"""R03创作数据访问；授权、发布编排和事务由服务层负责。"""

from sqlalchemy import delete, func, select

from app.database.models import (
    LearningNode,
    NodeResource,
    ReleaseNode,
    ReleaseResource,
    ReleaseStage,
    ReleaseStageEdge,
    RoadmapRelease,
    RoadmapStage,
    RoadmapStageEdge,
    SkillRoadmap,
    User,
)


async def get_route(session, route_id, *, lock=False):
    """读取路线头；写流程锁定并刷新已缓存对象。"""
    statement = select(SkillRoadmap).where(SkillRoadmap.id == route_id)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return await session.scalar(statement)


async def draft_rows(session, route_id, *, include_deleted=False):
    """按目标顺序读取工作稿，保留软删除身份供保存校验。"""
    stages = select(RoadmapStage).where(RoadmapStage.roadmap_id == route_id)
    nodes = select(LearningNode).where(LearningNode.roadmap_id == route_id)
    if not include_deleted:
        stages = stages.where(RoadmapStage.is_deleted == 0)
        nodes = nodes.where(LearningNode.is_deleted == 0)
    resources = (
        select(NodeResource)
        .join(LearningNode, NodeResource.node_id == LearningNode.id)
        .where(LearningNode.roadmap_id == route_id)
    )
    return (
        list(await session.scalars(stages.order_by(RoadmapStage.position))),
        list(await session.scalars(nodes.order_by(LearningNode.position))),
        list(await session.scalars(resources.order_by(NodeResource.position))),
    )


async def edges(session, route_id):
    """读取独立阶段边表。"""
    return list(
        await session.scalars(
            select(RoadmapStageEdge)
            .where(RoadmapStageEdge.roadmap_id == route_id)
            .order_by(RoadmapStageEdge.id)
        )
    )


async def release_edges(session, release_id):
    """读取冻结版连线。"""
    return list(
        await session.scalars(
            select(ReleaseStageEdge)
            .where(ReleaseStageEdge.release_id == release_id)
            .order_by(ReleaseStageEdge.id)
        )
    )


async def release_rows(session, release_id):
    """只读完整冻结版本。"""
    return (
        await session.get(RoadmapRelease, release_id),
        *[
            list(
                await session.scalars(
                    select(model).where(model.release_id == release_id).order_by(model.position)
                )
            )
            for model in (ReleaseStage, ReleaseNode, ReleaseResource)
        ],
    )


async def release_count(session, route_id):
    return await session.scalar(
        select(func.count())
        .select_from(RoadmapRelease)
        .where(RoadmapRelease.roadmap_id == route_id)
    )


async def author_routes(session, user_id, archived, state, query, page, page_size, **unused):
    """仓库只返回本人的路线头，一条路线一个条目。"""
    statement = select(SkillRoadmap).where(
        SkillRoadmap.creator_id == user_id,
        SkillRoadmap.author_archived_at.is_not(None)
        if archived
        else SkillRoadmap.author_archived_at.is_(None),
    )
    if state == "disabled":
        statement = statement.where(SkillRoadmap.moderation_status == "disabled")
    elif state:
        statement = statement.where(
            SkillRoadmap.distribution_status == ("draft" if state == "editing" else state)
        )
    if query:
        statement = statement.where(SkillRoadmap.title.contains(query, autoescape=True))
    total = await session.scalar(select(func.count()).select_from(statement.subquery()))
    rows = list(
        await session.scalars(
            statement.order_by(SkillRoadmap.updated_at.desc(), SkillRoadmap.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return total, rows


async def get_author(session, user_id):
    return await session.get(User, user_id)


async def moderation_routes(session, keyword, difficulty, status, sort_by, order, page, page_size):
    """只检索曾发布路线，搜索、筛选及分页均基于冻结版本，不接触私人工作稿。"""
    statement = (
        select(SkillRoadmap, RoadmapRelease, User)
        .join(RoadmapRelease, SkillRoadmap.current_release_id == RoadmapRelease.id)
        .join(User, SkillRoadmap.creator_id == User.id)
        .where(SkillRoadmap.roadmap_type == "user")
    )
    if keyword:
        statement = statement.where(RoadmapRelease.title.contains(keyword, autoescape=True))
    if difficulty:
        statement = statement.where(RoadmapRelease.difficulty == difficulty)
    if status == "disabled":
        statement = statement.where(SkillRoadmap.moderation_status == "disabled")
    elif status:
        statement = statement.where(
            SkillRoadmap.moderation_status == "normal",
            SkillRoadmap.distribution_status == status,
        )
    total = await session.scalar(select(func.count()).select_from(statement.subquery()))
    column = {
        "publishedAt": RoadmapRelease.published_at,
        "title": RoadmapRelease.title,
        "updatedAt": SkillRoadmap.updated_at,
    }[sort_by]
    ordering = column.asc() if order == "asc" else column.desc()
    rows = list(
        (
            await session.execute(
                statement.order_by(ordering, SkillRoadmap.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )
    return total, rows


async def route_releases(session, route_id):
    """返回同路线的发布版本，供审核切换，禁止跨路线快照引用。"""
    return list(
        await session.scalars(
            select(RoadmapRelease)
            .where(RoadmapRelease.roadmap_id == route_id)
            .order_by(RoadmapRelease.version_no.desc())
        )
    )


async def official_routes(session, archived, page, page_size, keyword="", status=None):
    """官方仓库供管理员共同维护，不按创建者分割。"""
    statement = select(SkillRoadmap).where(
        SkillRoadmap.roadmap_type == "official",
        SkillRoadmap.author_archived_at.is_not(None)
        if archived
        else SkillRoadmap.author_archived_at.is_(None),
    )
    if keyword:
        statement = statement.where(SkillRoadmap.title.contains(keyword, autoescape=True))
    if status == "disabled":
        statement = statement.where(SkillRoadmap.moderation_status == "disabled")
    elif status:
        statement = statement.where(
            SkillRoadmap.distribution_status == status, SkillRoadmap.moderation_status == "normal"
        )
    total = await session.scalar(select(func.count()).select_from(statement.subquery()))
    rows = list(
        await session.scalars(
            statement.order_by(SkillRoadmap.updated_at.desc(), SkillRoadmap.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return total, rows


async def moderation_history(session, route_id):
    """只返回此路线治理审计，不携带账号凭证或学习详情。"""
    from app.database.models import ModerationAction

    return list(
        await session.scalars(
            select(ModerationAction)
            .where(
                ModerationAction.target_type == "roadmap", ModerationAction.target_id == route_id
            )
            .order_by(ModerationAction.id.desc())
            .limit(30)
        )
    )


def add_moderation(
    session, actor_id, route_id, action, reason, before, after, request_id="internal"
):
    """在服务持有的事务中登记治理证据及安全审计。"""
    from app.database.models import AuditLog, ModerationAction

    session.add(
        ModerationAction(
            actor_id=actor_id,
            target_type="roadmap",
            target_id=route_id,
            action=action,
            reason=reason,
            before_state=before,
            after_state=after,
        )
    )
    session.add(
        AuditLog(
            actor_id=actor_id,
            action_code="roadmap." + action,
            target_type="roadmap",
            target_id=route_id,
            request_id=request_id,
            result="success",
            details={"reason": reason, "before": before, "after": after},
        )
    )


async def delete_draft_graph(session, route_id):
    """仅由验证无发布历史的服务事务调用，按外键依赖顺序显式清理。"""
    node_ids = select(LearningNode.id).where(LearningNode.roadmap_id == route_id)
    await session.execute(delete(NodeResource).where(NodeResource.node_id.in_(node_ids)))
    await session.execute(delete(LearningNode).where(LearningNode.roadmap_id == route_id))
    await session.execute(delete(RoadmapStageEdge).where(RoadmapStageEdge.roadmap_id == route_id))
    await session.execute(delete(RoadmapStage).where(RoadmapStage.roadmap_id == route_id))
    await session.execute(delete(SkillRoadmap).where(SkillRoadmap.id == route_id))
