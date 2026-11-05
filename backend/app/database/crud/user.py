"""账号、登录会话及隐私的数据库访问；不处理HTTP或提交事务。"""

from sqlalchemy import and_, exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.database.models import (
    ActivityEvent,
    AuditLog,
    RoadmapCheckin,
    RoadmapFavorite,
    RoadmapRelease,
    RoadmapSubscription,
    SkillRoadmap,
    User,
    UserAuthSession,
    UserFollow,
    UserPrivacySettings,
    UserRoadmap,
)


async def following_ids(session, user_id):
    """关注仅提供动态来源，不承担访问授权。"""
    return list(
        await session.scalars(
            select(UserFollow.followee_id).where(UserFollow.follower_id == user_id)
        )
    )


async def follow_state(session, viewer, target):
    """关注统计不包含停用或管理账号。"""

    async def count(column, other):
        return await session.scalar(
            select(func.count())
            .select_from(UserFollow)
            .join(User, User.id == other)
            .where(column == target, User.status == "active", User.role == "user")
        )

    return {
        "isFollowing": bool(
            await session.scalar(
                select(UserFollow.id).where(
                    UserFollow.follower_id == viewer, UserFollow.followee_id == target
                )
            )
        ),
        "followingCount": await count(UserFollow.follower_id, UserFollow.followee_id),
        "followerCount": await count(UserFollow.followee_id, UserFollow.follower_id),
    }


async def change_follow(session, viewer, target, enabled):
    """调用者已按用户ID排序加锁，唯一关系并发串行。"""
    row = await session.scalar(
        select(UserFollow)
        .where(UserFollow.follower_id == viewer, UserFollow.followee_id == target)
        .with_for_update()
    )
    if enabled and row is None:
        session.add(UserFollow(follower_id=viewer, followee_id=target))
    elif not enabled and row is not None:
        await session.delete(row)
    await session.flush()


async def following_rows(session, user_id, page, page_size):
    """本人关注列表按关系时间倒序分页。"""
    statement = (
        select(User)
        .join(UserFollow, UserFollow.followee_id == User.id)
        .where(UserFollow.follower_id == user_id, User.status == "active", User.role == "user")
    )
    return await paged(session, statement, page, page_size, UserFollow.id.desc())


async def relationship_rows(session, target, kind, viewer, page, page_size):
    """双向关系使用相同活跃成员过滤，批量联查查看者的关注状态。"""
    relation = aliased(UserFollow)
    other = UserFollow.followee_id if kind == "following" else UserFollow.follower_id
    owner = UserFollow.follower_id if kind == "following" else UserFollow.followee_id
    statement = (
        select(User, relation.id)
        .join(UserFollow, other == User.id)
        .outerjoin(relation, and_(relation.follower_id == viewer, relation.followee_id == User.id))
        .where(owner == target, User.status == "active", User.role == "user")
    )
    return await paged(session, statement, page, page_size, UserFollow.id.desc())


async def paged(session, statement, page, page_size, *ordering):
    """使用同一已过滤查询计数和分页，避免统计泄漏。"""
    total = await session.scalar(select(func.count()).select_from(statement.subquery()))
    rows = (
        await session.execute(
            statement.order_by(*ordering).offset((page - 1) * page_size).limit(page_size)
        )
    ).all()
    return total, rows


async def public_collection(session, user_id, category, page, page_size):
    """公开收藏与在学列表不选择关系ID、会话或进度。"""
    from app.database.crud.favorite import public_conditions

    model = RoadmapFavorite if category == "favorite" else UserRoadmap
    flag = (
        UserPrivacySettings.favorite_public
        if category == "favorite"
        else UserPrivacySettings.learning_public
    )
    statement = (
        select(SkillRoadmap, RoadmapRelease, User)
        .join(RoadmapRelease, SkillRoadmap.current_release_id == RoadmapRelease.id)
        .join(User, SkillRoadmap.creator_id == User.id)
        .join(model, model.roadmap_id == SkillRoadmap.id)
        .join(UserPrivacySettings, UserPrivacySettings.user_id == model.user_id)
        .where(model.user_id == user_id, flag == 1, *public_conditions())
    )
    if category == "learning":
        statement = statement.where(UserRoadmap.status == "active")
    return await paged(session, statement, page, page_size, model.id.desc())


async def own_collection_counts(session, user_id):
    """本人数量包含保留的私密关系；他人数量仍走公开过滤查询。"""
    result = []
    for model in (RoadmapFavorite, UserRoadmap):
        statement = select(func.count()).select_from(model).where(model.user_id == user_id)
        if model is UserRoadmap:
            statement = statement.where(model.status == "active")
        result.append(await session.scalar(statement))
    return result


async def activity_rows(session, actors, page, page_size, viewer=None):
    """路线发布、话题发布及有效打卡先过滤，再合并排序与分页；不展示回复或关系动态。"""
    from sqlalchemy import literal, null, union_all

    from app.database.crud.favorite import public_conditions
    from app.database.models import RoadmapIssue

    actor = aliased(User)
    event_release = aliased(RoadmapRelease)
    events = (
        select(
            ActivityEvent.actor_id.label("actor_id"),
            actor.nickname.label("nickname"),
            actor.avatar_url.label("avatar_url"),
            ActivityEvent.activity_type.label("activity_type"),
            ActivityEvent.occurred_on.label("occurred_on"),
            func.max(ActivityEvent.created_at).label("created_at"),
            func.concat("event:", func.max(ActivityEvent.id)).label("id"),
            func.count().label("route_count"),
            func.min(SkillRoadmap.id).label("roadmap_id"),
            func.min(RoadmapRelease.title).label("title"),
            null().label("issue_id"),
        )
        .join(actor, actor.id == ActivityEvent.actor_id)
        .join(UserPrivacySettings, UserPrivacySettings.user_id == actor.id)
        .join(SkillRoadmap, SkillRoadmap.id == ActivityEvent.roadmap_id)
        .join(RoadmapRelease, RoadmapRelease.id == SkillRoadmap.current_release_id)
        .join(User, User.id == SkillRoadmap.creator_id)
        .where(
            ActivityEvent.actor_id.in_(actors),
            actor.status == "active",
            or_(ActivityEvent.actor_id == viewer, ActivityEvent.visibility == "public"),
            ActivityEvent.is_active == 1,
            *public_conditions(),
            or_(
                and_(
                    ActivityEvent.activity_type == "publish",
                    or_(actor.id == viewer, UserPrivacySettings.publish_public == 1),
                    exists(
                        select(event_release.id).where(
                            event_release.id == ActivityEvent.release_id,
                            event_release.content_access == "normal",
                        )
                    ),
                ),
                and_(
                    ActivityEvent.activity_type == "checkin",
                    or_(actor.id == viewer, UserPrivacySettings.checkin_public == 1),
                    exists(
                        select(RoadmapCheckin.id).where(
                            RoadmapCheckin.id == ActivityEvent.checkin_id,
                            RoadmapCheckin.is_valid == 1,
                        )
                    ),
                ),
            ),
        )
        .group_by(
            ActivityEvent.actor_id,
            actor.nickname,
            actor.avatar_url,
            ActivityEvent.activity_type,
            ActivityEvent.occurred_on,
            func.if_(ActivityEvent.activity_type == "checkin", 0, ActivityEvent.id),
        )
    )
    # 话题表本身就是发布事实，按当前标题和可见状态投影；不复制正文或产生回复事件。
    topics = (
        select(
            RoadmapIssue.author_id.label("actor_id"),
            actor.nickname.label("nickname"),
            actor.avatar_url.label("avatar_url"),
            literal("topic").label("activity_type"),
            func.date(func.convert_tz(RoadmapIssue.created_at, "+00:00", "+08:00")).label(
                "occurred_on"
            ),
            RoadmapIssue.created_at.label("created_at"),
            func.concat("topic:", RoadmapIssue.id).label("id"),
            literal(1).label("route_count"),
            SkillRoadmap.id.label("roadmap_id"),
            RoadmapIssue.title.label("title"),
            RoadmapIssue.id.label("issue_id"),
        )
        .join(actor, actor.id == RoadmapIssue.author_id)
        .join(UserPrivacySettings, UserPrivacySettings.user_id == actor.id)
        .join(SkillRoadmap, SkillRoadmap.id == RoadmapIssue.roadmap_id)
        .join(RoadmapRelease, RoadmapRelease.id == SkillRoadmap.current_release_id)
        .join(User, User.id == SkillRoadmap.creator_id)
        .where(
            RoadmapIssue.author_id.in_(actors),
            actor.status == "active",
            RoadmapIssue.visibility == "public",
            or_(actor.id == viewer, UserPrivacySettings.topic_public == 1),
            *public_conditions(),
        )
    )
    combined = union_all(events, topics).subquery()
    return await paged(
        session,
        select(combined),
        page,
        page_size,
        combined.c.created_at.desc(),
        combined.c.id.desc(),
    )


async def record_activity(
    session, actor_id, route_id, kind, key, occurred_on, *, checkin_id=None, release_id=None
):
    """只写必要引用；分类私密不销毁事实，以便重新公开时恢复有效事件。"""
    session.add(
        ActivityEvent(
            actor_id=actor_id,
            roadmap_id=route_id,
            activity_type=kind,
            event_key=key,
            occurred_on=occurred_on,
            checkin_id=checkin_id,
            release_id=release_id,
            visibility="public",
            is_active=1,
        )
    )
    await session.flush()


async def deactivate_activity(session, actor_id, route_id, kind):
    """取消关系永久使旧事件失效，重建关系时生成新事件。"""
    await session.execute(
        update(ActivityEvent)
        .where(
            ActivityEvent.actor_id == actor_id,
            ActivityEvent.roadmap_id == route_id,
            ActivityEvent.activity_type == kind,
            ActivityEvent.is_active == 1,
        )
        .values(is_active=0)
    )


async def roadmap_subscription(session, user_id, route_id, *, lock=False):
    """显式退订保留一行，不被收藏、学习或关注覆盖。"""
    statement = select(RoadmapSubscription).where(
        RoadmapSubscription.user_id == user_id, RoadmapSubscription.roadmap_id == route_id
    )
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return await session.scalar(statement)


async def get_by_username(
    session: AsyncSession, username: str, *, lock: bool = False
) -> User | None:
    """按规范化账号查询，锁定读取时刷新会话中的旧对象。"""
    statement = select(User).where(User.username == username)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return (await session.execute(statement)).scalar_one_or_none()


async def get_by_id(session: AsyncSession, user_id: int, *, lock: bool = False) -> User | None:
    """按ID查询账号，不联查私人学习数据。"""
    statement = select(User).where(User.id == user_id)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return (await session.execute(statement)).scalar_one_or_none()


async def add_user(session: AsyncSession, **values) -> User:
    """只写入账号，默认隐私的原子编排由服务层负责。"""
    user = User(**values)
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


async def add_privacy(session: AsyncSession, user_id: int) -> UserPrivacySettings:
    """使用数据库默认值初始化隐私，不提交事务。"""
    privacy = UserPrivacySettings(user_id=user_id)
    session.add(privacy)
    await session.flush()
    await session.refresh(privacy)
    return privacy


async def get_privacy(session, user_id, *, lock=False):
    """读取本人设置；写入时使用行锁及最新版本。"""
    statement = select(UserPrivacySettings).where(UserPrivacySettings.user_id == user_id)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return (await session.execute(statement)).scalar_one_or_none()


async def get_auth_session(session, user_id, session_key, *, lock=False):
    """查询令牌引用的会话，不能只按JWT中的用户ID认定有效。"""
    statement = select(UserAuthSession).where(
        UserAuthSession.user_id == user_id, UserAuthSession.session_key == session_key
    )
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return (await session.execute(statement)).scalar_one_or_none()


async def add_auth_session(session, **values):
    """持久化随机登录会话引用，不存明文JWT。"""
    row = UserAuthSession(**values)
    session.add(row)
    await session.flush()
    return row


async def revoke_sessions(session, user_id, now, *, session_key=None):
    """撤销当前或全部未撤销会话，保留原有撤销证据。"""
    statement = update(UserAuthSession).where(
        UserAuthSession.user_id == user_id, UserAuthSession.revoked_at.is_(None)
    )
    if session_key is not None:
        statement = statement.where(UserAuthSession.session_key == session_key)
    await session.execute(statement.values(revoked_at=now, updated_at=now))


async def add_audit(session, **values):
    """审计与账号写入同事务；调用方只传必要状态，不传密码或令牌。"""
    session.add(AuditLog(**values))
    await session.flush()


async def list_accounts(session, keyword, role, status, page, page_size):
    """返回账号资料及分页，不扩展管理员对个人学习数据的访问。"""
    statement = select(User)
    if keyword:
        statement = statement.where(
            or_(
                User.username.contains(keyword, autoescape=True),
                User.nickname.contains(keyword, autoescape=True),
            )
        )
    if role is not None:
        statement = statement.where(User.role == role)
    if status is not None:
        statement = statement.where(User.status == status)
    total = await session.scalar(select(func.count()).select_from(statement.subquery()))
    rows = (
        await session.scalars(
            statement.order_by(User.created_at.desc(), User.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return total, rows


async def delivery_counts(session):
    """系统维护只读取投递状态数量，不暴露消息正文或收件人。"""
    from app.database.models import NotificationOutbox

    rows = (
        await session.execute(
            select(NotificationOutbox.status, func.count()).group_by(NotificationOutbox.status)
        )
    ).all()
    return dict(rows)


async def audit_rows(session, page, page_size):
    """管理员审计分页只读，不提供任意查询数据库的接口。"""
    total = await session.scalar(select(func.count()).select_from(AuditLog))
    rows = list(
        await session.scalars(
            select(AuditLog)
            .order_by(AuditLog.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return total, rows


async def failed_deliveries(session):
    """仅取最近20条失败任务，不向管理端返回投递载荷与收件人。"""
    from app.database.models import NotificationOutbox

    return list(
        await session.scalars(
            select(NotificationOutbox)
            .where(NotificationOutbox.status == "failed")
            .order_by(NotificationOutbox.updated_at.desc(), NotificationOutbox.id.desc())
            .limit(20)
        )
    )
