"""outbox租约、接收者及通知幂等存取。"""

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.mysql import insert

from app.database.models import (
    IssueSubscription,
    Notification,
    NotificationOutbox,
    RoadmapSubscription,
    User,
)


async def claimable(session, stamp):
    """跳过其他进程持锁任务；过期processing允许重新认领。"""
    return await session.scalar(
        select(NotificationOutbox)
        .where(
            or_(
                and_(
                    NotificationOutbox.status == "pending", NotificationOutbox.available_at <= stamp
                ),
                and_(
                    NotificationOutbox.status == "processing",
                    NotificationOutbox.lease_until <= stamp,
                ),
            )
        )
        .order_by(NotificationOutbox.id)
        .limit(1)
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    )


async def leased(session, task_id):
    """租约确认使用当前数据库值。"""
    return await session.scalar(
        select(NotificationOutbox)
        .where(NotificationOutbox.id == task_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def subscribers(session, topic_id=None, route_id=None):
    """投递时再读取显式退订与账号状态。"""
    model = IssueSubscription if topic_id is not None else RoadmapSubscription
    target = model.issue_id == topic_id if topic_id is not None else model.roadmap_id == route_id
    return set(
        await session.scalars(
            select(model.user_id)
            .join(User, User.id == model.user_id)
            .where(target, model.is_subscribed == 1, User.status == "active")
        )
    )


async def put_notification(session, **values):
    """重复投递不覆盖read_at/deleted_at，已读状态和收件人删除意图均保留。"""
    stmt = insert(Notification).values(**values)
    await session.execute(stmt.on_duplicate_key_update(id=Notification.id))


async def active_recipients(session, recipients):
    """投递前按当前账号状态过滤接收者。"""
    return set(
        await session.scalars(
            select(User.id).where(User.id.in_(recipients), User.status == "active")
        )
    )


async def notification_rows(session, user_id, page, page_size, unread):
    """只分页当前用户的通知。"""
    cond = [Notification.recipient_id == user_id, Notification.deleted_at.is_(None)]
    if unread:
        cond.append(Notification.read_at.is_(None))
    total = await session.scalar(select(func.count()).select_from(Notification).where(*cond))
    rows = list(
        await session.scalars(
            select(Notification)
            .where(*cond)
            .order_by(Notification.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return total, rows


async def unread_count(session, user_id):
    """本人未读计数。"""
    return await session.scalar(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.recipient_id == user_id,
            Notification.read_at.is_(None),
            Notification.deleted_at.is_(None),
        )
    )


async def mark_read(session, user_id, stamp, notification_id=None, through_id=None):
    """保留已有已读时间，批量读取不影响边界之后的消息。"""
    cond = [
        Notification.recipient_id == user_id,
        Notification.read_at.is_(None),
        Notification.deleted_at.is_(None),
    ]
    cond.append(
        Notification.id == notification_id if notification_id else Notification.id <= through_id
    )
    await session.execute(update(Notification).where(*cond).values(read_at=stamp))


async def latest_notification_id(session, user_id):
    """收件箱可见消息水位，不随未读筛选或分页改变。"""
    return await session.scalar(
        select(func.max(Notification.id)).where(
            Notification.recipient_id == user_id, Notification.deleted_at.is_(None)
        )
    )


async def remove_notifications(
    session, user_id, stamp, notification_id=None, through_id=None, read_only=False
):
    """只软删除本人且边界内的消息，原去重键和删除时间不覆盖。"""
    cond = [Notification.recipient_id == user_id, Notification.deleted_at.is_(None)]
    cond.append(
        Notification.id == notification_id if notification_id else Notification.id <= through_id
    )
    if read_only:
        cond.append(Notification.read_at.is_not(None))
    result = await session.execute(update(Notification).where(*cond).values(deleted_at=stamp))
    return result.rowcount
