"""R08单目标举报、审计和治理事务，禁止管理员读取私人学习详情。"""

from app.core.exceptions import AppError
from app.core.security import utc_now
from app.database.crud import moderation as crud
from app.database.crud import roadmap as roadmaps
from app.database.crud import user as users
from app.database.models import ContentReport
from app.schemas.common import serialize_utc
from app.services.auth_service import authenticated_account
from app.services.issue_service import accessible_route


def missing():
    return AppError(404, "REPORT_TARGET_NOT_FOUND", "举报或目标不存在或不可访问")


def target_identity(report):
    """数据库单目标约束对应的受控字段映射。"""
    for kind in ("roadmap", "issue", "comment"):
        value = getattr(report, kind + "_id")
        if value is not None:
            return kind, value
    raise missing()


def report_summary(row):
    """任何列表均不返回举报人身份，普通用户只能查询本人结果。"""
    kind, target_id = target_identity(row)
    return {
        "id": str(row.id),
        "targetType": kind,
        "targetId": str(target_id),
        "reasonCode": row.reason_code,
        "description": row.description,
        "status": row.status,
        "resultNote": row.result_note,
        "createdAt": serialize_utc(row.created_at),
        "handledAt": serialize_utc(row.handled_at) if row.handled_at else None,
    }


class ModerationService:
    """写入统一路线→管理员/举报人→举报→目标，保留引用和学习事实。"""

    def __init__(self, session, request_id="internal"):
        self.session, self.request_id = session, request_id

    async def admin(self, claims, *, lock=False):
        """事务内复核管理员身份，撤销会话和角色变化即时生效。"""
        actor = await authenticated_account(self.session, claims, lock=lock)
        if actor.role != "admin":
            raise AppError(403, "ADMIN_REQUIRED", "需要管理员权限")
        return actor

    async def create(self, claims, data):
        """只举报当前可访问内容，同目标未结案举报复用，避免重复堆积。"""
        async with self.session.begin():
            target = await crud.get_target(self.session, data.target_type, data.target_id)
            if target is None:
                raise missing()
            route_id = await crud.target_route_id(self.session, data.target_type, target)
            await accessible_route(self.session, route_id, claims.user_id, lock=True)
            actor = await authenticated_account(self.session, claims, lock=True)
            if actor.role != "user":
                raise AppError(403, "ADMIN_COMMUNITY_FORBIDDEN", "管理账号不提交社区举报")
            target = await crud.get_target(
                self.session, data.target_type, data.target_id, lock=True
            )
            if target is None:
                raise missing()
            author_id = target.creator_id if data.target_type == "roadmap" else target.author_id
            if author_id == claims.user_id:
                raise AppError(
                    403,
                    "SELF_REPORT_FORBIDDEN",
                    "不能举报自己发布的内容，请使用编辑、删除或撤回功能",
                )
            if data.target_type != "roadmap" and target.visibility != "public":
                raise missing()
            if data.target_type == "comment":
                topic = await crud.get_target(self.session, "issue", target.issue_id)
                if not topic or topic.visibility != "public":
                    raise missing()
            column = getattr(ContentReport, data.target_type + "_id")
            existing = await crud.duplicate_report(
                self.session, claims.user_id, column, data.target_id
            )
            if existing:
                return report_summary(existing)
            row = ContentReport(
                reporter_id=claims.user_id,
                reason_code=data.reason_code,
                description=data.description,
                **{data.target_type + "_id": data.target_id},
            )
            self.session.add(row)
            await self.session.flush()
            await self.session.refresh(row)
            return report_summary(row)

    async def listing(self, claims, admin, status, page, page_size):
        """治理列表不扩大到学习详情，普通列表固定当前举报人。"""
        async with self.session.begin():
            if admin:
                await self.admin(claims)
            else:
                await authenticated_account(self.session, claims)
            total, rows = await crud.reports(
                self.session, None if admin else claims.user_id, status, page, page_size
            )
            return {
                "items": [report_summary(r) for r in rows],
                "total": total,
                "page": page,
                "pageSize": page_size,
            }

    async def detail(self, claims, report_id):
        """授权审核只返回举报目标必要内容，删除内容仍保留占位。"""
        async with self.session.begin():
            await self.admin(claims)
            report = await crud.get_report(self.session, report_id)
            if not report:
                raise missing()
            kind, target_id = target_identity(report)
            target = await crud.get_target(self.session, kind, target_id)
            result = report_summary(report)
            result["target"] = None
            if target:
                route_id = await crud.target_route_id(self.session, kind, target)
                if kind == "roadmap":
                    release = await roadmaps.route_releases(self.session, route_id)
                    result["target"] = {
                        "roadmapId": str(route_id),
                        "title": release[0].title if release else "路线不可访问",
                        "body": None,
                        "visibility": target.moderation_status,
                    }
                else:
                    visible = target.visibility != "deleted"
                    result["target"] = {
                        "roadmapId": str(route_id),
                        "title": getattr(target, "title", "回复") if visible else "内容已删除",
                        "body": target.body if visible else None,
                        "visibility": target.visibility,
                    }
            return result

    async def handle(self, claims, report_id, data):
        """结案与目标治理原子提交；不以举报结案默认删除原内容。"""
        async with self.session.begin():
            report = await crud.get_report(self.session, report_id)
            if not report:
                raise missing()
            kind, target_id = target_identity(report)
            target = await crud.get_target(self.session, kind, target_id)
            if target is None:
                raise missing()
            route_id = await crud.target_route_id(self.session, kind, target)
            route = await roadmaps.get_route(self.session, route_id, lock=True)
            await self.admin(claims, lock=True)
            report = await crud.get_report(self.session, report_id, lock=True)
            if report.status != data.expected_status:
                raise AppError(409, "REPORT_STATUS_CONFLICT", "举报状态已变化，请重新加载")
            if data.status != "resolved" and data.action != "none":
                raise AppError(422, "INVALID_MODERATION_ACTION", "仅确认有效并结案时可执行治理")
            target = await crud.get_target(self.session, kind, target_id, lock=True)
            if data.action != "none":
                if kind == "roadmap" and data.action in {"disable", "restore"}:
                    before = {"moderationStatus": route.moderation_status}
                    route.moderation_status = "disabled" if data.action == "disable" else "normal"
                    route.edit_version += 1
                    route.updated_at = utc_now()
                    after = {"moderationStatus": route.moderation_status}
                elif (
                    kind in {"issue", "comment"}
                    and data.action in {"hide", "restore"}
                    and target.visibility != "deleted"
                ):
                    before = {"visibility": target.visibility}
                    target.visibility = "hidden" if data.action == "hide" else "public"
                    target.updated_at = utc_now()
                    after = {"visibility": target.visibility}
                else:
                    raise AppError(
                        422, "INVALID_MODERATION_ACTION", "动作不适用于此目标，已删除内容不能恢复"
                    )
                crud.add_action(
                    self.session,
                    claims.user_id,
                    kind,
                    target_id,
                    data.action,
                    data.reason,
                    before,
                    after,
                    report.id,
                    request_id=self.request_id,
                )
            previous = report.status
            report.status, report.result_note = data.status, data.reason
            report.handled_by = claims.user_id
            report.handled_at = utc_now() if data.status in {"resolved", "rejected"} else None
            report.updated_at = utc_now()
            await users.add_audit(
                self.session,
                actor_id=claims.user_id,
                action_code="report." + data.status,
                target_type="report",
                target_id=report.id,
                request_id=self.request_id,
                result="success",
                details={
                    "before": previous,
                    "after": data.status,
                    "action": data.action,
                    "reason": data.reason,
                },
            )
            return report_summary(report)

    async def invalidate_checkin(self, claims, checkin_id, data):
        """精确撤销打卡有效性，统计从is_valid事实重新计算，不读取私人进度。"""
        async with self.session.begin():
            target = await crud.get_target(self.session, "checkin", checkin_id)
            if target is None:
                raise missing()
            route_id = await crud.target_route_id(self.session, "checkin", target)
            await roadmaps.get_route(self.session, route_id, lock=True)
            await self.admin(claims, lock=True)
            target = await crud.get_target(self.session, "checkin", checkin_id, lock=True)
            if bool(target.is_valid) != data.expected_valid:
                raise AppError(409, "CHECKIN_STATE_CONFLICT", "打卡有效状态已变化")
            if target.is_valid:
                target.is_valid, target.invalidated_at, target.invalidated_by = (
                    0,
                    utc_now(),
                    claims.user_id,
                )
                crud.add_action(
                    self.session,
                    claims.user_id,
                    "checkin",
                    target.id,
                    "invalidate",
                    data.reason,
                    {"isValid": True},
                    {"isValid": False},
                    request_id=self.request_id,
                )
            return {"id": str(target.id), "isValid": False}
