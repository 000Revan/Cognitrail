"""收藏关系与公开卡片查询；不决定业务权限或提交事务。"""

from sqlalchemy import func, or_, select

from app.database.models import (
    ReleaseNode,
    ReleaseStage,
    RoadmapFavorite,
    RoadmapRelease,
    SkillRoadmap,
    User,
    UserRoadmap,
)


def public_conditions():
    """与服务层公开可见性一致，先过滤再计数与分页。"""
    return (
        SkillRoadmap.distribution_status == "published",
        SkillRoadmap.author_archived_at.is_(None),
        SkillRoadmap.moderation_status == "normal",
        RoadmapRelease.content_access == "normal",
        RoadmapRelease.roadmap_id == SkillRoadmap.id,
        or_(SkillRoadmap.roadmap_type == "official", User.status == "active"),
    )


async def public_routes(
    session, query, difficulty, page, page_size, sort_by="publishedAt", order="desc", author_id=None
):
    """搜索和排序全部使用当前冻结版，不读取作者工作稿。"""
    statement = (
        select(SkillRoadmap, RoadmapRelease, User)
        .join(RoadmapRelease, SkillRoadmap.current_release_id == RoadmapRelease.id)
        .join(User, SkillRoadmap.creator_id == User.id)
        .where(*public_conditions())
    )
    if query:
        statement = statement.where(RoadmapRelease.title.contains(query, autoescape=True))
    if author_id is not None:
        statement = statement.where(SkillRoadmap.creator_id == author_id)
    if difficulty:
        statement = statement.where(RoadmapRelease.difficulty == difficulty)
    total = await session.scalar(select(func.count()).select_from(statement.subquery()))
    # 先聚合再关联，按完整结果集排序后分页，避免多版本学习与收藏JOIN放大。
    if sort_by == "learnerCount":
        counts = (
            select(
                UserRoadmap.roadmap_id.label("roadmap_id"),
                func.count(UserRoadmap.user_id.distinct()).label("value"),
            )
            .group_by(UserRoadmap.roadmap_id)
            .subquery()
        )
    elif sort_by == "favoriteCount":
        counts = (
            select(
                RoadmapFavorite.roadmap_id.label("roadmap_id"),
                func.count().label("value"),
            )
            .group_by(RoadmapFavorite.roadmap_id)
            .subquery()
        )
    else:
        counts = None
    if counts is not None:
        statement = statement.outerjoin(counts, counts.c.roadmap_id == SkillRoadmap.id)
        sort_column = func.coalesce(counts.c.value, 0)
    else:
        sort_column = RoadmapRelease.published_at
    ascending = order == "asc"
    ordering = [sort_column.asc() if ascending else sort_column.desc()]
    if counts is not None:
        ordering.append(RoadmapRelease.published_at.desc())
    ordering.append(SkillRoadmap.id.asc() if ascending else SkillRoadmap.id.desc())
    rows = (
        await session.execute(
            statement.order_by(*ordering).offset((page - 1) * page_size).limit(page_size)
        )
    ).all()
    return total, rows


async def engagement_counts(session, route_ids, viewer):
    """学习人数跨版本去重；收藏和学习分别查询，防止JOIN乘积。"""
    if not route_ids:
        return {}, {}, set()
    learners = dict(
        (
            await session.execute(
                select(UserRoadmap.roadmap_id, func.count(UserRoadmap.user_id.distinct()))
                .where(UserRoadmap.roadmap_id.in_(route_ids))
                .group_by(UserRoadmap.roadmap_id)
            )
        ).all()
    )
    favorites = dict(
        (
            await session.execute(
                select(RoadmapFavorite.roadmap_id, func.count())
                .where(RoadmapFavorite.roadmap_id.in_(route_ids))
                .group_by(RoadmapFavorite.roadmap_id)
            )
        ).all()
    )
    mine = (
        set(
            (
                await session.scalars(
                    select(RoadmapFavorite.roadmap_id).where(
                        RoadmapFavorite.roadmap_id.in_(route_ids), RoadmapFavorite.user_id == viewer
                    )
                )
            ).all()
        )
        if viewer is not None
        else set()
    )
    return learners, favorites, mine


async def release_counts(session, release_ids):
    """批量统计冻结结构，避免把未发布节点算入社区卡片。"""
    result = []
    for model in (ReleaseStage, ReleaseNode):
        result.append(
            dict(
                (
                    await session.execute(
                        select(model.release_id, func.count())
                        .where(model.release_id.in_(release_ids))
                        .group_by(model.release_id)
                    )
                ).all()
            )
            if release_ids
            else {}
        )
    return result


async def favorite_rows(session, user_id, page, page_size):
    """本人列表保留不可公开访问的关系，按收藏时间稳定倒序。"""
    statement = (
        select(RoadmapFavorite, SkillRoadmap, RoadmapRelease, User)
        .join(SkillRoadmap, RoadmapFavorite.roadmap_id == SkillRoadmap.id)
        .outerjoin(RoadmapRelease, SkillRoadmap.current_release_id == RoadmapRelease.id)
        .join(User, SkillRoadmap.creator_id == User.id)
        .where(RoadmapFavorite.user_id == user_id)
    )
    total = await session.scalar(select(func.count()).select_from(statement.subquery()))
    rows = (
        await session.execute(
            statement.order_by(RoadmapFavorite.created_at.desc(), RoadmapFavorite.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return total, rows


async def get_favorite(session, route_id, user_id):
    """路线行锁后采用当前读，串行化同路线的收藏与取消。"""
    return await session.scalar(
        select(RoadmapFavorite)
        .where(RoadmapFavorite.roadmap_id == route_id, RoadmapFavorite.user_id == user_id)
        .with_for_update()
    )


async def favorite_count(session, route_id):
    """返回当前保留关系数量，包含来源受限的收藏。"""
    return await session.scalar(
        select(func.count())
        .select_from(RoadmapFavorite)
        .where(RoadmapFavorite.roadmap_id == route_id)
    )


async def public_structure(session, release_id):
    """只投影公开目录列，不查询节点正文、提示、资源或个人学习状态。"""
    stages = (
        await session.execute(
            select(
                ReleaseStage.id, ReleaseStage.title, ReleaseStage.canvas_x, ReleaseStage.canvas_y
            )
            .where(ReleaseStage.release_id == release_id)
            .order_by(ReleaseStage.position)
        )
    ).all()
    nodes = (
        await session.execute(
            select(
                ReleaseNode.id,
                ReleaseNode.stage_id,
                ReleaseNode.title,
                ReleaseNode.canvas_x,
                ReleaseNode.canvas_y,
            )
            .where(ReleaseNode.release_id == release_id)
            .order_by(ReleaseNode.position)
        )
    ).all()
    return stages, nodes
