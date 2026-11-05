"""仅清理R03测试随机账号创建的路线，绝不清库或接触开发账号。"""

from sqlalchemy import delete, or_, select, update

from app.database.models import (
    ActivityEvent,
    ContentReport,
    IssueComment,
    IssueEvent,
    IssueSubscription,
    LearningNode,
    LearningSession,
    LearningSessionEvent,
    ModerationAction,
    NodeResource,
    Notification,
    NotificationOutbox,
    ReleaseNode,
    ReleaseResource,
    ReleaseStage,
    ReleaseStageEdge,
    ResourceVisit,
    RoadmapCheckin,
    RoadmapFavorite,
    RoadmapIssue,
    RoadmapRelease,
    RoadmapStage,
    RoadmapStageEdge,
    RoadmapSubscription,
    SkillRoadmap,
    User,
    UserNodeProgress,
    UserRoadmap,
)


async def cleanup_routes(database, usernames):
    """先按精确随机账号取ID，再解除循环指针并按外键依赖清理本次夹具。"""
    assert usernames and all(name.startswith("r02_") and len(name) >= 24 for name in usernames)
    async with database.sessions() as session, session.begin():
        user_ids = select(User.id).where(User.username.in_(usernames))
        route_ids = list(
            await session.scalars(
                select(SkillRoadmap.id).where(SkillRoadmap.creator_id.in_(user_ids))
            )
        )
        if not route_ids:
            return
        await session.execute(
            delete(ModerationAction).where(
                ModerationAction.target_type == "roadmap", ModerationAction.target_id.in_(route_ids)
            )
        )
        issue_ids = list(
            await session.scalars(
                select(RoadmapIssue.id).where(RoadmapIssue.roadmap_id.in_(route_ids))
            )
        )
        comment_ids = list(
            await session.scalars(
                select(IssueComment.id).where(IssueComment.issue_id.in_(issue_ids))
            )
        )
        reports_query = select(ContentReport.id).where(
            or_(
                ContentReport.reporter_id.in_(user_ids),
                ContentReport.roadmap_id.in_(route_ids),
                ContentReport.issue_id.in_(issue_ids),
                ContentReport.comment_id.in_(comment_ids),
            )
        )
        reports = list(await session.scalars(reports_query))
        await session.execute(
            delete(ModerationAction).where(
                or_(
                    ModerationAction.report_id.in_(reports), ModerationAction.actor_id.in_(user_ids)
                )
            )
        )
        await session.execute(delete(ContentReport).where(ContentReport.id.in_(reports)))
        issue_events = list(
            await session.scalars(select(IssueEvent.id).where(IssueEvent.issue_id.in_(issue_ids)))
        )
        discussion_keys = (
            [f"issue:{i}:created" for i in issue_ids]
            + [f"comment:{i}:created" for i in comment_ids]
            + [f"issue-event:{i}" for i in issue_events]
        )
        await session.execute(delete(Notification).where(Notification.roadmap_id.in_(route_ids)))
        await session.execute(
            delete(NotificationOutbox).where(NotificationOutbox.event_key.in_(discussion_keys))
        )
        await session.execute(
            delete(IssueSubscription).where(IssueSubscription.issue_id.in_(issue_ids))
        )
        await session.execute(delete(IssueEvent).where(IssueEvent.issue_id.in_(issue_ids)))
        await session.execute(
            update(IssueComment)
            .where(IssueComment.issue_id.in_(issue_ids))
            .values(reply_to_comment_id=None)
        )
        await session.execute(delete(IssueComment).where(IssueComment.issue_id.in_(issue_ids)))
        await session.execute(delete(RoadmapIssue).where(RoadmapIssue.id.in_(issue_ids)))
        await session.execute(
            delete(RoadmapSubscription).where(RoadmapSubscription.roadmap_id.in_(route_ids))
        )
        relations = list(
            await session.scalars(
                select(UserRoadmap.id).where(UserRoadmap.roadmap_id.in_(route_ids))
            )
        )
        learning_ids = list(
            await session.scalars(
                select(LearningSession.id).where(LearningSession.user_roadmap_id.in_(relations))
            )
        )
        # 活动引用打卡来源，必须先解除引用再清理日期事实。
        await session.execute(delete(ActivityEvent).where(ActivityEvent.roadmap_id.in_(route_ids)))
        await session.execute(
            delete(RoadmapCheckin).where(RoadmapCheckin.user_roadmap_id.in_(relations))
        )
        await session.execute(
            delete(LearningSessionEvent).where(LearningSessionEvent.user_roadmap_id.in_(relations))
        )
        await session.execute(
            update(UserRoadmap).where(UserRoadmap.id.in_(relations)).values(current_session_id=None)
        )
        await session.execute(
            update(UserNodeProgress)
            .where(UserNodeProgress.session_id.in_(learning_ids))
            .values(source_progress_id=None)
        )
        await session.execute(
            delete(UserNodeProgress).where(UserNodeProgress.session_id.in_(learning_ids))
        )
        await session.execute(
            update(LearningSession)
            .where(LearningSession.id.in_(learning_ids))
            .values(source_session_id=None)
        )
        await session.execute(
            delete(ResourceVisit).where(ResourceVisit.session_id.in_(learning_ids))
        )
        await session.execute(delete(LearningSession).where(LearningSession.id.in_(learning_ids)))
        await session.execute(delete(UserRoadmap).where(UserRoadmap.id.in_(relations)))
        await session.execute(
            delete(RoadmapFavorite).where(RoadmapFavorite.roadmap_id.in_(route_ids))
        )
        releases = list(
            await session.scalars(
                select(RoadmapRelease.id).where(RoadmapRelease.roadmap_id.in_(route_ids))
            )
        )
        event_keys = [f"release:{i}:published" for i in releases]
        await session.execute(
            delete(NotificationOutbox).where(NotificationOutbox.event_key.in_(event_keys))
        )
        await session.execute(delete(ActivityEvent).where(ActivityEvent.roadmap_id.in_(route_ids)))
        await session.execute(
            update(SkillRoadmap)
            .where(SkillRoadmap.id.in_(route_ids))
            .values(current_release_id=None)
        )
        for model in (ReleaseResource, ReleaseStageEdge, ReleaseNode, ReleaseStage):
            await session.execute(delete(model).where(model.release_id.in_(releases)))
        await session.execute(delete(RoadmapRelease).where(RoadmapRelease.id.in_(releases)))
        nodes = select(LearningNode.id).where(LearningNode.roadmap_id.in_(route_ids))
        await session.execute(delete(NodeResource).where(NodeResource.node_id.in_(nodes)))
        for model in (LearningNode, RoadmapStageEdge, RoadmapStage, SkillRoadmap):
            column = model.id if model is SkillRoadmap else model.roadmap_id
            await session.execute(delete(model).where(column.in_(route_ids)))
