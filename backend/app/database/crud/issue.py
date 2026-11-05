"""话题存取与锁定；事务、授权和响应由服务层处理。"""

from sqlalchemy import case, func, select

from app.database.models import IssueComment, IssueEvent, IssueSubscription, RoadmapIssue, User


async def my_discussions(session, user_id, kind, page, page_size):
    """本人提问/回复先过滤目标及治理状态，再计数分页；不返回其他人的正文。"""
    from sqlalchemy import and_, exists, or_

    from app.database.crud.user import paged
    from app.database.models import RoadmapRelease, SkillRoadmap, UserRoadmap

    statement = select(RoadmapIssue, RoadmapRelease.title.label("route_title"))
    if kind == "replies":
        statement = (
            select(RoadmapIssue, RoadmapRelease.title.label("route_title"), IssueComment)
            .join(IssueComment, IssueComment.issue_id == RoadmapIssue.id)
            .where(IssueComment.author_id == user_id, IssueComment.visibility == "public")
        )
        ordering = IssueComment.created_at.desc(), IssueComment.id.desc()
    else:
        statement = statement.where(RoadmapIssue.author_id == user_id)
        ordering = RoadmapIssue.created_at.desc(), RoadmapIssue.id.desc()
    statement = (
        statement.join(SkillRoadmap, SkillRoadmap.id == RoadmapIssue.roadmap_id)
        .join(RoadmapRelease, RoadmapRelease.id == SkillRoadmap.current_release_id)
        .join(User, User.id == SkillRoadmap.creator_id)
        .where(
            RoadmapIssue.visibility == "public",
            SkillRoadmap.moderation_status == "normal",
            RoadmapRelease.content_access == "normal",
            or_(SkillRoadmap.roadmap_type == "official", User.status == "active"),
            or_(
                and_(
                    SkillRoadmap.distribution_status == "published",
                    SkillRoadmap.author_archived_at.is_(None),
                ),
                SkillRoadmap.creator_id == user_id,
                exists(
                    select(UserRoadmap.id).where(
                        UserRoadmap.user_id == user_id, UserRoadmap.roadmap_id == SkillRoadmap.id
                    )
                ),
            ),
        )
    )
    return await paged(session, statement, page, page_size, *ordering)


async def get_issue(session, issue_id, lock=False):
    """锁定查询刷新身份映射，避免并发关闭后仍沿用旧状态。"""
    stmt = select(RoadmapIssue).where(RoadmapIssue.id == issue_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return await session.scalar(stmt)


async def get_comment(session, issue_id, comment_id):
    """联合归属校验，不允许跨话题锚点。"""
    return await session.scalar(
        select(IssueComment).where(IssueComment.id == comment_id, IssueComment.issue_id == issue_id)
    )


async def list_issues(
    session, route_id, status, page, page_size, sort_by="createdAt", order="desc"
):
    """先过滤隐藏和删除，再计数分页。"""
    conditions = [RoadmapIssue.roadmap_id == route_id, RoadmapIssue.visibility == "public"]
    if status:
        conditions.append(RoadmapIssue.status == status)
    total = await session.scalar(select(func.count()).select_from(RoadmapIssue).where(*conditions))
    rows = list(
        await session.scalars(
            select(RoadmapIssue)
            .where(*conditions)
            .order_by(
                (
                    RoadmapIssue.created_at
                    if sort_by == "createdAt"
                    else RoadmapIssue.last_activity_at
                ).asc()
                if order == "asc"
                else (
                    RoadmapIssue.created_at
                    if sort_by == "createdAt"
                    else RoadmapIssue.last_activity_at
                ).desc(),
                RoadmapIssue.id.asc() if order == "asc" else RoadmapIssue.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return total, rows


def comment_tree(issue_id, root_ids=None):
    """遍历原始引用链；删除节点仅承担连接后续回复的内部身份。"""
    conditions = [IssueComment.issue_id == issue_id, IssueComment.reply_to_comment_id.is_(None)]
    if root_ids is not None:
        conditions.append(IssueComment.id.in_(root_ids))
    tree = (
        select(IssueComment.id, IssueComment.id.label("root_id"))
        .where(*conditions)
        .cte("thread_tree", recursive=True)
    )
    return tree.union_all(
        select(IssueComment.id, tree.c.root_id)
        .join(tree, IssueComment.reply_to_comment_id == tree.c.id)
        .where(IssueComment.issue_id == issue_id)
    )


def visible_threads(issue_id):
    """已删除且没有存活回复的楼层不参与分页，避免空楼层与错误页数。"""
    tree = comment_tree(issue_id)
    return (
        select(tree.c.root_id)
        .join(IssueComment, IssueComment.id == tree.c.id)
        .where(IssueComment.visibility != "deleted")
        .distinct()
    )


async def comments(session, issue_id, page, page_size):
    """按根评论分页，子回复保留在同组，不占独立楼层。"""
    condition = IssueComment.id.in_(visible_threads(issue_id))
    total = await session.scalar(select(func.count()).select_from(IssueComment).where(condition))
    rows = list(
        await session.scalars(
            select(IssueComment)
            .where(condition)
            .order_by(IssueComment.created_at, IssueComment.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return total, rows


async def events(session, issue_id):
    """时间线按发生顺序输出。"""
    return list(
        await session.scalars(
            select(IssueEvent).where(IssueEvent.issue_id == issue_id).order_by(IssueEvent.id)
        )
    )


async def subscription(session, issue_id, user_id):
    """在话题锁保护下获取唯一订阅。"""
    return await session.scalar(
        select(IssueSubscription).where(
            IssueSubscription.issue_id == issue_id, IssueSubscription.user_id == user_id
        )
    )


async def duplicate_body(session, user_id, issue_id, body, since):
    """提示短时间内同用户同话题的重复正文；不影响正常后续讨论。"""
    return await session.scalar(
        select(IssueComment.id)
        .where(
            IssueComment.author_id == user_id,
            IssueComment.issue_id == issue_id,
            IssueComment.body == body,
            IssueComment.created_at >= since,
            IssueComment.visibility == "public",
        )
        .limit(1)
    )


async def preceding_comments(session, issue_id, comment_id):
    """锚点前的回复数量用于计算页码，与单话题锁下生成顺序一致。"""
    return await session.scalar(
        select(func.count())
        .select_from(IssueComment)
        .where(
            IssueComment.issue_id == issue_id,
            IssueComment.id <= comment_id,
            IssueComment.reply_to_comment_id.is_(None),
            IssueComment.id.in_(visible_threads(issue_id)),
        )
    )


async def comment_authors(session, rows):
    """批量读取本页回复作者。"""
    return {
        u.id: u
        for u in await session.scalars(select(User).where(User.id.in_({r.author_id for r in rows})))
    }


async def duplicate_issue(session, route_id, user_id, title, body, since):
    """同一路线短时重复话题检查。"""
    return await session.scalar(
        select(RoadmapIssue.id)
        .where(
            RoadmapIssue.roadmap_id == route_id,
            RoadmapIssue.author_id == user_id,
            RoadmapIssue.title == title,
            RoadmapIssue.body == body,
            RoadmapIssue.created_at >= since,
            RoadmapIssue.visibility == "public",
        )
        .limit(1)
    )


async def issue_statistics(session, route_id):
    """统计整条路线的可见话题，不随分页和状态筛选改变。"""
    rows = (
        await session.execute(
            select(RoadmapIssue.status, func.count())
            .where(RoadmapIssue.roadmap_id == route_id, RoadmapIssue.visibility == "public")
            .group_by(RoadmapIssue.status)
        )
    ).all()
    counts = dict(rows)
    return sum(counts.values()), counts.get("closed", 0)


async def comment_counts(session, issue_ids):
    """批量统计未删除的评论，与实际展示数量一致。"""
    return dict(
        (
            await session.execute(
                select(IssueComment.issue_id, func.count())
                .where(IssueComment.issue_id.in_(issue_ids), IssueComment.visibility != "deleted")
                .group_by(IssueComment.issue_id)
            )
        ).all()
    )


async def root_comment(session, issue_id, comment_id):
    """沿既有同话题引用回溯根评论，兼容旧的多层回复链。"""
    ancestry = (
        select(IssueComment.id, IssueComment.reply_to_comment_id)
        .where(
            IssueComment.issue_id == issue_id,
            IssueComment.id == comment_id,
            IssueComment.visibility != "deleted",
        )
        .cte("ancestors", recursive=True)
    )
    ancestry = ancestry.union_all(
        select(IssueComment.id, IssueComment.reply_to_comment_id)
        .join(ancestry, IssueComment.id == ancestry.c.reply_to_comment_id)
        .where(IssueComment.issue_id == issue_id)
    )
    return await session.scalar(
        select(ancestry.c.id).where(ancestry.c.reply_to_comment_id.is_(None))
    )


async def thread_replies(
    session, issue_id, root_ids, anchor=None, requested_page=None, page_size=5
):
    """按根评论批量取楼中楼分页，单组预览有界；锚点自动展开其所在页。"""
    if not root_ids:
        return {}
    tree = comment_tree(issue_id, root_ids)
    totals = dict(
        (
            await session.execute(
                select(tree.c.root_id, func.count())
                .join(IssueComment, IssueComment.id == tree.c.id)
                .where(tree.c.id != tree.c.root_id, IssueComment.visibility != "deleted")
                .group_by(tree.c.root_id)
            )
        ).all()
    )
    ranked = (
        select(
            tree.c.id,
            tree.c.root_id,
            func.row_number()
            .over(partition_by=tree.c.root_id, order_by=tree.c.id)
            .label("position"),
        )
        .join(IssueComment, IssueComment.id == tree.c.id)
        .where(tree.c.id != tree.c.root_id, IssueComment.visibility != "deleted")
        .subquery()
    )
    anchor_row = (
        (
            await session.execute(
                select(ranked.c.root_id, ranked.c.position).where(ranked.c.id == anchor)
            )
        ).first()
        if anchor
        else None
    )
    pages = {
        rid: (
            requested_page
            or (
                (anchor_row.position - 1) // page_size + 1
                if anchor_row and anchor_row.root_id == rid
                else 1
            )
        )
        for rid in root_ids
    }
    starts = case(pages, value=ranked.c.root_id, else_=1) * page_size - page_size
    rows = (
        await session.execute(
            select(IssueComment, ranked.c.root_id)
            .join(ranked, IssueComment.id == ranked.c.id)
            .where(ranked.c.position > starts, ranked.c.position <= starts + page_size)
            .order_by(ranked.c.root_id, IssueComment.id)
        )
    ).all()
    grouped = {
        rid: {"rows": [], "total": totals.get(rid, 0), "page": pages[rid], "pageSize": page_size}
        for rid in root_ids
    }
    for row, rid in rows:
        grouped[rid]["rows"].append(row)
    return grouped


async def reply_targets(session, rows):
    """批量获取直接被回复对象，隐藏或删除内容由服务层掩码。"""
    return {
        r.id: r
        for r in await session.scalars(
            select(IssueComment).where(
                IssueComment.id.in_({r.reply_to_comment_id for r in rows if r.reply_to_comment_id})
            )
        )
    }
