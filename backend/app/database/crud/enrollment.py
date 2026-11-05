"""R05 数据访问：本人关系、当前会话与日期事实，事务由服务编排。"""

from sqlalchemy import func, select

from app.database.models import (
    LearningSession,
    LearningSessionEvent,
    ReleaseNode,
    ReleaseResource,
    ReleaseStage,
    ReleaseStageEdge,
    RoadmapCheckin,
    RoadmapRelease,
    SkillRoadmap,
    UserNodeProgress,
    UserRoadmap,
)


def current_read(statement, lock):
    """等待行锁后刷新映射，避免使用锁定前的旧状态。"""
    return (
        statement.with_for_update().execution_options(populate_existing=True) if lock else statement
    )


async def get_enrollment(session, enrollment_id, user_id, *, lock=False):
    return await session.scalar(
        current_read(
            select(UserRoadmap).where(
                UserRoadmap.id == enrollment_id, UserRoadmap.user_id == user_id
            ),
            lock,
        )
    )


async def find_enrollment(session, user_id, roadmap_id, *, lock=False):
    return await session.scalar(
        current_read(
            select(UserRoadmap).where(
                UserRoadmap.user_id == user_id, UserRoadmap.roadmap_id == roadmap_id
            ),
            lock,
        )
    )


async def get_session(session, relation, *, lock=False):
    return await session.scalar(
        current_read(
            select(LearningSession).where(
                LearningSession.id == relation.current_session_id,
                LearningSession.user_roadmap_id == relation.id,
                LearningSession.roadmap_id == relation.roadmap_id,
            ),
            lock,
        )
    )


async def enrollment_rows(session, user_id, status, page, page_size):
    """每条路线只有一条学习关系，退出记录通过显式筛选读取。"""
    statement = (
        select(UserRoadmap, SkillRoadmap, LearningSession, RoadmapRelease)
        .join(SkillRoadmap, SkillRoadmap.id == UserRoadmap.roadmap_id)
        .join(LearningSession, LearningSession.id == UserRoadmap.current_session_id)
        .join(RoadmapRelease, RoadmapRelease.id == LearningSession.release_id)
        .where(UserRoadmap.user_id == user_id, UserRoadmap.status == (status or "active"))
    )
    total = await session.scalar(select(func.count()).select_from(statement.subquery()))
    rows = (
        await session.execute(
            statement.order_by(UserRoadmap.started_at.desc(), UserRoadmap.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return total, rows


async def get_node(session, release_id, node_id):
    return await session.scalar(
        select(ReleaseNode).where(ReleaseNode.id == node_id, ReleaseNode.release_id == release_id)
    )


async def get_progress(session, session_id, node_id):
    return await session.scalar(
        current_read(
            select(UserNodeProgress).where(
                UserNodeProgress.session_id == session_id,
                UserNodeProgress.release_node_id == node_id,
            ),
            True,
        )
    )


async def progress_rows(session, session_id, *, lock=False):
    return list(
        (
            await session.scalars(
                current_read(
                    select(UserNodeProgress)
                    .where(UserNodeProgress.session_id == session_id)
                    .order_by(UserNodeProgress.id),
                    lock,
                )
            )
        ).all()
    )


async def progress_counts(session, learning, *, lock=False):
    """写事务以当前读统计，避免等待关系锁前建立的RR快照漏算并发完成。"""
    nodes = select(ReleaseNode.id).where(
        ReleaseNode.release_id == learning.release_id,
        ReleaseNode.counts_toward_progress == 1,
    )
    completed = select(UserNodeProgress.release_node_id).where(
        UserNodeProgress.session_id == learning.id,
        UserNodeProgress.is_completed == 1,
    )
    if lock:
        # 冻结目录只加共享锁；个人进度按固定ID顺序当前读，防止陈旧统计。
        nodes = nodes.with_for_update(read=True)
        completed = completed.order_by(UserNodeProgress.id).with_for_update()
    node_ids = set(await session.scalars(nodes))
    completed_ids = set(await session.scalars(completed))
    return len(completed_ids & node_ids), len(node_ids)


async def record_for_day(session, relation_id, today):
    """包含治理撤销记录；撤销不释放当天再次打卡资格。"""
    return await session.scalar(
        current_read(
            select(RoadmapCheckin).where(
                RoadmapCheckin.user_roadmap_id == relation_id, RoadmapCheckin.checkin_date == today
            ),
            True,
        )
    )


async def record_rows(session, relation_id, page, page_size):
    statement = select(RoadmapCheckin).where(RoadmapCheckin.user_roadmap_id == relation_id)
    total = await session.scalar(select(func.count()).select_from(statement.subquery()))
    rows = list(
        (
            await session.scalars(
                statement.order_by(RoadmapCheckin.checkin_date.desc(), RoadmapCheckin.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )
    return total, rows


async def checkin_dates(session, user_id):
    """先限定本人，再跨路线按有效自然日去重，退出与来源状态不删除日期事实。"""
    return list(
        (
            await session.scalars(
                select(RoadmapCheckin.checkin_date)
                .join(UserRoadmap, UserRoadmap.id == RoadmapCheckin.user_roadmap_id)
                .where(UserRoadmap.user_id == user_id, RoadmapCheckin.is_valid == 1)
                .distinct()
                .order_by(RoadmapCheckin.checkin_date)
            )
        ).all()
    )


async def overview_counts(session, user_id):
    learning = await session.scalar(
        select(func.count())
        .select_from(UserRoadmap)
        .where(UserRoadmap.user_id == user_id, UserRoadmap.status == "active")
    )
    completed = await session.scalar(
        select(func.count())
        .select_from(UserNodeProgress)
        .join(LearningSession, LearningSession.id == UserNodeProgress.session_id)
        .join(UserRoadmap, UserRoadmap.current_session_id == LearningSession.id)
        .where(UserRoadmap.user_id == user_id, UserNodeProgress.is_completed == 1)
    )
    return learning or 0, completed or 0


async def get_release(session, release_id, *, lock=False):
    """写事务使用共享锁当前读，防止等锁前的RR快照隐藏新版本或治理变化。"""
    statement = select(RoadmapRelease).where(RoadmapRelease.id == release_id)
    if lock:
        statement = statement.with_for_update(read=True).execution_options(populate_existing=True)
    return await session.scalar(statement)


async def release_graph(session, release_id, *, lock=False):
    """返回冻结图原始记录；写事务只加共享锁，不编辑任何发布快照。"""
    result = []
    for model in (ReleaseStage, ReleaseNode, ReleaseResource, ReleaseStageEdge):
        statement = select(model).where(model.release_id == release_id).order_by(model.id)
        if lock:
            statement = statement.with_for_update(read=True).execution_options(
                populate_existing=True
            )
        result.append(list(await session.scalars(statement)))
    return result


async def event_by_key(session, relation_id, key):
    """关系锁内按请求键当前读，检查已提交事件及请求语义。"""
    return await session.scalar(
        current_read(
            select(LearningSessionEvent).where(
                LearningSessionEvent.user_roadmap_id == relation_id,
                LearningSessionEvent.request_key == key,
            ),
            True,
        )
    )


async def get_session_by_id(session, relation_id, session_id):
    """历史会话同样严格限定本人已获授权关系，不能按任意会话ID读取。"""
    return await session.scalar(
        select(LearningSession).where(
            LearningSession.id == session_id, LearningSession.user_roadmap_id == relation_id
        )
    )


async def session_rows(session, relation_id, page, page_size):
    """本人版本历史分页；不修改任何旧会话。"""
    statement = (
        select(LearningSession, RoadmapRelease)
        .join(RoadmapRelease, RoadmapRelease.id == LearningSession.release_id)
        .where(LearningSession.user_roadmap_id == relation_id)
    )
    total = await session.scalar(select(func.count()).select_from(statement.subquery()))
    rows = (
        await session.execute(
            statement.order_by(LearningSession.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return total, rows
