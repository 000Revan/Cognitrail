"""账号、隐私及社区作者主页服务，关系、活动与审计遵守事务边界。"""

import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.enums import UserRole
from app.core.exceptions import AppError
from app.core.security import AuthClaims, hash_password, utc_now, verify_password
from app.database.crud import user as crud
from app.domain.account_policy import require_current_user
from app.schemas.user import (
    MAX_SETTINGS_VERSION,
    PasswordUpdate,
    PrivacySettings,
    ProfileUpdate,
    UserPublic,
)
from app.services.auth_service import authenticated_account
from app.services.avatar_service import AvatarStore

logger = logging.getLogger(__name__)


class UserService:
    """服务层拥有事务；写操作先锁用户及登录会话，再修改目标状态。"""

    def __init__(
        self,
        session: AsyncSession,
        request_id: str = "internal",
        avatars: AvatarStore | None = None,
    ) -> None:
        self.session = session
        self.request_id = request_id
        self.avatars = avatars

    async def system_info(self, claims, settings):
        """白名单返回运行参数，不序列化环境对象或数据库凭证。"""
        from app.schemas.common import serialize_utc

        async with self.session.begin():
            user = await authenticated_account(self.session, claims)
            if user.role != UserRole.ADMIN:
                raise AppError(403, "ADMIN_REQUIRED", "需要管理员权限")
            return {
                "appName": settings.app_name,
                "timezone": settings.app_timezone,
                "sessionSeconds": settings.access_token_seconds,
                "loginLimit": settings.login_rate_limit,
                "loginWindowSeconds": settings.login_rate_window_seconds,
                "outboxEnabled": settings.outbox_enabled,
                "outboxMaxAttempts": settings.outbox_max_attempts,
                "deliveryCounts": await crud.delivery_counts(self.session),
                "failedDeliveries": [
                    {
                        "id": str(row.id),
                        "eventType": row.event_type,
                        "attempts": row.attempts,
                        "errorType": row.last_error,
                        "updatedAt": serialize_utc(row.updated_at),
                    }
                    for row in await crud.failed_deliveries(self.session)
                ],
            }

    async def audit_listing(self, claims, page, page_size):
        """审计上下文按字段白名单展示，拒绝输出潜在正文或凭证。"""
        from app.schemas.common import serialize_utc

        async with self.session.begin():
            self.require_admin(await authenticated_account(self.session, claims))
            total, rows = await crud.audit_rows(self.session, page, page_size)
            return {
                "items": [
                    {
                        "id": str(r.id),
                        "actorId": str(r.actor_id) if r.actor_id else None,
                        "action": r.action_code,
                        "targetType": r.target_type,
                        "targetId": str(r.target_id) if r.target_id else None,
                        "result": r.result,
                        "createdAt": serialize_utc(r.created_at),
                        "details": {
                            k: v
                            for k, v in (r.details or {}).items()
                            if k in {"reason", "before", "after", "role", "action"}
                        }
                        if isinstance(r.details, dict)
                        else {},
                    }
                    for r in rows
                ],
                "total": total,
                "page": page,
                "pageSize": page_size,
            }

    async def public_profile(self, claims, user_id, page, page_size):
        """登录后展示资料、可见作品及公开分类计数，不读取私人学习进度。"""
        from app.database.crud import favorite as public_crud
        from app.services.favorite_service import FavoriteService

        async with self.session.begin():
            self.require_community(await authenticated_account(self.session, claims))
            user = await crud.get_by_id(self.session, user_id)
            if not user or user.status != "active":
                raise AppError(404, "USER_NOT_FOUND", "用户不存在或不可访问")
            total, rows = await public_crud.public_routes(
                self.session, "", None, page, page_size, author_id=user_id
            )
            own_counts = (
                await crud.own_collection_counts(self.session, user_id)
                if user_id == claims.user_id
                else None
            )
            privacy = await crud.get_privacy(self.session, user_id)
            favorites_visible = own_counts is not None or bool(privacy and privacy.favorite_public)
            learning_visible = own_counts is not None or bool(privacy and privacy.learning_public)
            return {
                "id": str(user.id),
                "username": user.username,
                "nickname": user.nickname,
                "avatarUrl": user.avatar_url,
                "bio": user.bio,
                **await crud.follow_state(self.session, claims.user_id, user_id),
                "canFollow": user.role == "user" and user.id != claims.user_id,
                "canViewFavorites": favorites_visible,
                "canViewLearning": learning_visible,
                "favoriteCount": None
                if not favorites_visible
                else own_counts[0]
                if own_counts
                else (await crud.public_collection(self.session, user_id, "favorite", 1, 1))[0],
                "learningCount": None
                if not learning_visible
                else own_counts[1]
                if own_counts
                else (await crud.public_collection(self.session, user_id, "learning", 1, 1))[0],
                "roadmaps": {
                    "items": await FavoriteService(self.session).cards(rows, claims.user_id),
                    "total": total,
                    "page": page,
                    "pageSize": page_size,
                },
            }

    @staticmethod
    def require_community(user):
        """管理账号不参与普通社区关系或活动。"""
        if user.role != "user":
            raise AppError(403, "ADMIN_COMMUNITY_FORBIDDEN", "管理账号不参与社区，请使用普通账号")
        return user

    @staticmethod
    def identity(user):
        """只投影社区公开身份字段。"""
        return {
            "id": str(user.id),
            "username": user.username,
            "nickname": user.nickname,
            "avatarUrl": user.avatar_url,
            "bio": user.bio,
        }

    async def follow(self, claims, target_id, enabled):
        """按ID排序锁定双方，防止互相关注死锁；操作与计数原子提交。"""
        async with self.session.begin():
            users = {}
            for uid in sorted({claims.user_id, target_id}):
                users[uid] = await crud.get_by_id(self.session, uid, lock=True)
            self.require_community(await authenticated_account(self.session, claims, lock=True))
            target = users[target_id]
            if target_id == claims.user_id:
                raise AppError(403, "SELF_FOLLOW_FORBIDDEN", "不能关注自己")
            if not target or target.role != "user" or (enabled and target.status != "active"):
                raise AppError(404, "USER_NOT_FOUND", "用户不存在或不可访问")
            await crud.change_follow(self.session, claims.user_id, target_id, enabled)
            return await crud.follow_state(self.session, claims.user_id, target_id)

    async def following(self, claims, page, page_size):
        """本人关注列表，不读取被关注者私人资料。"""
        async with self.session.begin():
            self.require_community(await authenticated_account(self.session, claims))
            total, rows = await crud.following_rows(self.session, claims.user_id, page, page_size)
            return {
                "items": [self.identity(row[0]) for row in rows],
                "total": total,
                "page": page,
                "pageSize": page_size,
            }

    async def relationships(self, claims, target_id, kind, page, page_size):
        """公开关系不开放私人资料，按钮状态按查看者计算。"""
        async with self.session.begin():
            self.require_community(await authenticated_account(self.session, claims))
            target = await crud.get_by_id(self.session, target_id)
            if not target or target.status != "active":
                raise AppError(404, "USER_NOT_FOUND", "用户不存在或不可访问")
            total, rows = await crud.relationship_rows(
                self.session, target_id, kind, claims.user_id, page, page_size
            )
            last_page = max(1, (total + page_size - 1) // page_size)
            if page > last_page:
                page = last_page
                total, rows = await crud.relationship_rows(
                    self.session, target_id, kind, claims.user_id, page, page_size
                )
            return {
                "items": [
                    {
                        **self.identity(user),
                        "isFollowing": bool(relation_id),
                        "canFollow": user.id != claims.user_id,
                    }
                    for user, relation_id in rows
                ],
                "total": total,
                "page": page,
                "pageSize": page_size,
            }

    async def activities(self, claims, page, page_size, target_id=None):
        """作者动态或关注动态使用相同服务端过滤，禁止前端先取私密事实。"""
        from app.schemas.common import serialize_utc

        async with self.session.begin():
            self.require_community(await authenticated_account(self.session, claims))
            if target_id is not None:
                target = await crud.get_by_id(self.session, target_id)
                if not target or target.status != "active":
                    raise AppError(404, "USER_NOT_FOUND", "用户不存在或不可访问")
                actors = [target_id]
            else:
                actors = await crud.following_ids(self.session, claims.user_id)
            total, rows = await crud.activity_rows(
                self.session, actors, page, page_size, claims.user_id
            )
            return {
                "items": [
                    {
                        "id": str(r.id),
                        "actorId": str(r.actor_id),
                        "nickname": r.nickname,
                        "avatarUrl": r.avatar_url,
                        "activityType": r.activity_type,
                        "occurredOn": r.occurred_on.isoformat(),
                        "createdAt": serialize_utc(r.created_at),
                        "routeCount": r.route_count,
                        "roadmapId": str(r.roadmap_id) if r.route_count == 1 else None,
                        "title": r.title if r.route_count == 1 else None,
                        "issueId": str(r.issue_id) if r.issue_id is not None else None,
                    }
                    for r in rows
                ],
                "total": total,
                "page": page,
                "pageSize": page_size,
            }

    async def collections(self, claims, target_id, category, page, page_size):
        """分类列表只返回公开路线卡片，私密与空列表使用同一响应。"""
        from app.services.favorite_service import FavoriteService

        async with self.session.begin():
            self.require_community(await authenticated_account(self.session, claims))
            target = await crud.get_by_id(self.session, target_id)
            if not target or target.status != "active":
                raise AppError(404, "USER_NOT_FOUND", "用户不存在或不可访问")
            total, rows = await crud.public_collection(
                self.session, target_id, category, page, page_size
            )
            return {
                "items": await FavoriteService(self.session).cards(rows, claims.user_id),
                "total": total,
                "page": page,
                "pageSize": page_size,
            }

    async def discussions(self, claims, kind, page, page_size):
        """个人提问与回复入口，不构建跨路线公共问答首页。"""
        from app.database.crud.issue import my_discussions
        from app.schemas.common import serialize_utc

        async with self.session.begin():
            self.require_community(await authenticated_account(self.session, claims))
            total, rows = await my_discussions(self.session, claims.user_id, kind, page, page_size)
            items = []
            for row in rows:
                topic = row[0]
                comment = row[2] if kind == "replies" else None
                items.append(
                    {
                        "id": str(comment.id if comment else topic.id),
                        "issueId": str(topic.id),
                        "roadmapId": str(topic.roadmap_id),
                        "roadmapTitle": row[1],
                        "title": topic.title,
                        "body": comment.body if comment else topic.body,
                        "status": topic.status,
                        "commentId": str(comment.id) if comment else None,
                        "createdAt": serialize_utc(
                            comment.created_at if comment else topic.created_at
                        ),
                    }
                )
            return {"items": items, "total": total, "page": page, "pageSize": page_size}

    async def update_avatar(self, claims: AuthClaims, stream) -> UserPublic:
        """上传后重新锁定校验当前会话；提交成功后才清理旧头像。"""
        assert self.avatars is not None
        new_url = await self.avatars.save(stream)
        try:
            async with self.session.begin():
                user = await authenticated_account(self.session, claims, lock=True)
                old_url = user.avatar_url
                user.avatar_url = new_url
                user.updated_at = utc_now()
                await self.session.flush()
                result = UserPublic.model_validate(user)
        except BaseException:
            # 提交连接中断时结果可能不确定，确认未被引用后才清理新文件。
            try:
                async with self.session.begin():
                    current = await crud.get_by_id(self.session, claims.user_id, lock=True)
                    referenced = current is not None and current.avatar_url == new_url
                if not referenced:
                    await self.avatars.remove(new_url)
            except Exception:
                logger.warning("Avatar rollback cleanup deferred")
            raise
        try:
            await self.avatars.remove(old_url)
        except OSError:
            logger.warning("Old avatar cleanup deferred")
        return result

    @staticmethod
    def require_admin(user):
        """角色只取当前数据库账号，管理员不因此获得他人的隐私设置。"""
        if user.role != UserRole.ADMIN:
            raise AppError(403, "ADMIN_REQUIRED", "需要管理员权限")
        return user

    async def audit(self, claims, target_id, action, details=None):
        """只保存必要操作结果，与账号变更使用同一事务。"""
        await crud.add_audit(
            self.session,
            actor_id=claims.user_id,
            action_code=action,
            target_type="user",
            target_id=target_id,
            request_id=self.request_id,
            result="success",
            details=details,
        )

    async def accounts(self, claims, keyword, role, status, page, page_size):
        """管理员列表仅输出公开账号资料，不联查私人数据。"""
        async with self.session.begin():
            self.require_admin(await authenticated_account(self.session, claims))
            total, rows = await crud.list_accounts(
                self.session, keyword.strip(), role, status, page, page_size
            )
            return {
                "items": [UserPublic.model_validate(row) for row in rows],
                "total": total,
                "page": page,
                "pageSize": page_size,
            }

    async def create_account(self, claims, data):
        """账号与默认隐私原子创建，客户端不能修改既有账号角色。"""
        try:
            async with self.session.begin():
                self.require_admin(await authenticated_account(self.session, claims, lock=True))
                if await crud.get_by_username(self.session, data.username):
                    raise AppError(409, "USERNAME_EXISTS", "该用户名已被使用")
                user = await crud.add_user(
                    self.session,
                    username=data.username,
                    nickname=data.nickname or data.username,
                    password_hash=await hash_password(data.password.get_secret_value()),
                    role=data.role.value,
                )
                await crud.add_privacy(self.session, user.id)
                await self.audit(claims, user.id, "account.create", {"role": data.role.value})
                return UserPublic.model_validate(user)
        except IntegrityError as error:
            if error.orig.args and error.orig.args[0] == 1062:
                raise AppError(409, "USERNAME_EXISTS", "该用户名已被使用") from error
            raise

    async def locked_account(self, claims, user_id):
        """按用户ID升序锁定操作者/目标，再锁会话，避免交叉管理死锁。"""
        locked = {}
        for target_id in sorted({claims.user_id, user_id}):
            locked[target_id] = await crud.get_by_id(self.session, target_id, lock=True)
        login = await crud.get_auth_session(
            self.session, claims.user_id, claims.session_key, lock=True
        )
        self.require_admin(require_current_user(locked[claims.user_id], claims, login))
        if locked[user_id] is None:
            raise AppError(404, "USER_NOT_FOUND", "账号不存在")
        return locked[user_id]

    async def edit_account(self, claims, user_id, data):
        """按原昵称检测冲突，不修改用户名、角色或本人隐私。"""
        async with self.session.begin():
            target = await self.locked_account(claims, user_id)
            if target.nickname != data.expected_nickname:
                raise AppError(409, "ACCOUNT_PROFILE_CONFLICT", "昵称已变化，请刷新后重新编辑")
            target.nickname = data.nickname
            target.updated_at = utc_now()
            await self.audit(claims, target.id, "account.nickname")
            return UserPublic.model_validate(target)

    async def reset_account_password(self, claims, user_id, data):
        """重置普通用户密码并撤销其全部会话；管理员使用本人改密流程。"""
        async with self.session.begin():
            target = await self.locked_account(claims, user_id)
            if target.role == UserRole.ADMIN:
                raise AppError(409, "ADMIN_ACCOUNT_PROTECTED", "管理员请在账号设置中修改本人密码")
            now = utc_now()
            target.password_hash = await hash_password(data.new_password.get_secret_value())
            target.updated_at = now
            await crud.revoke_sessions(self.session, user_id, now)
            await self.audit(claims, target.id, "account.password_reset")

    async def set_account_status(self, claims, user_id, data):
        """状态写入、会话撤销和审计同事务；启用不能恢复已撤销凭证。"""
        async with self.session.begin():
            target = await self.locked_account(claims, user_id)
            if target.role == UserRole.ADMIN:
                raise AppError(409, "ADMIN_ACCOUNT_PROTECTED", "管理员账号不支持在此修改状态")
            if target.status == data.status:
                return UserPublic.model_validate(target)
            if target.status != data.expected_status:
                raise AppError(409, "ACCOUNT_STATUS_CONFLICT", "账号状态已变化，请刷新后重新确认")
            now = utc_now()
            before = target.status
            target.status = data.status
            target.deactivated_at = now if data.status == "disabled" else None
            target.updated_at = now
            await crud.revoke_sessions(self.session, user_id, now)
            await self.audit(
                claims, target.id, "account.status", {"before": before, "after": data.status}
            )
            return UserPublic.model_validate(target)

    async def update_profile(self, claims: AuthClaims, data: ProfileUpdate) -> UserPublic:
        """仅修改本人显式资料字段，角色和状态字段不接受客户端输入。"""
        async with self.session.begin():
            user = await authenticated_account(self.session, claims, lock=True)
            for field in data.model_fields_set:
                setattr(user, field, getattr(data, field))
            user.updated_at = utc_now()
            await self.session.flush()
            return UserPublic.model_validate(user)

    async def change_password(self, claims: AuthClaims, data: PasswordUpdate) -> None:
        """验证原密码后原子换哈希并撤销所有会话，不签发隐式新凭证。"""
        async with self.session.begin():
            user = await authenticated_account(self.session, claims, lock=True)
            if not await verify_password(data.old_password.get_secret_value(), user.password_hash):
                raise AppError(409, "OLD_PASSWORD_MISMATCH", "原密码不正确")
            now = utc_now()
            user.password_hash = await hash_password(data.new_password.get_secret_value())
            user.updated_at = now
            await crud.revoke_sessions(self.session, user.id, now)

    async def privacy(self, claims):
        """只读取本人当前分类设置，不开放他人设置查询。"""
        async with self.session.begin():
            await authenticated_account(self.session, claims)
            row = await crud.get_privacy(self.session, claims.user_id)
            if row is None:
                raise AppError(503, "PRIVACY_NOT_INITIALIZED", "账号隐私设置未初始化")
            return PrivacySettings.model_validate(row)

    async def update_privacy(self, claims, data):
        """按settings_version拒绝过期更新；同值不制造新版本。"""
        async with self.session.begin():
            await authenticated_account(self.session, claims, lock=True)
            row = await crud.get_privacy(self.session, claims.user_id, lock=True)
            if row is None:
                raise AppError(503, "PRIVACY_NOT_INITIALIZED", "账号隐私设置未初始化")
            if row.settings_version != data.settings_version:
                raise AppError(409, "PRIVACY_VERSION_CONFLICT", "隐私设置已变化，请重新加载后确认")
            fields = ("publish_public", "checkin_public", "favorite_public", "learning_public")
            if "topic_public" in data.model_fields_set:
                fields += ("topic_public",)
            if any(bool(getattr(row, field)) != getattr(data, field) for field in fields):
                if row.settings_version == MAX_SETTINGS_VERSION:
                    raise AppError(
                        409, "PRIVACY_VERSION_EXHAUSTED", "设置版本已达上限，请联系管理员"
                    )
                for field in fields:
                    setattr(row, field, int(getattr(data, field)))
                row.settings_version += 1
                row.updated_at = utc_now()
                await self.session.flush()
            return PrivacySettings.model_validate(row)
