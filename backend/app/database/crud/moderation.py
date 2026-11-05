"""举报数据访问；权限与状态编排由治理服务负责。"""

from sqlalchemy import func, select

from app.database.models import (
    AuditLog,
    ContentReport,
    IssueComment,
    ModerationAction,
    RoadmapCheckin,
    RoadmapIssue,
    UserRoadmap,
)


async def get_target(session, kind, target_id, *, lock=False):
    """多态目标由固定模型映射解析，不拼接SQL标识符。"""
    from app.database.models import SkillRoadmap

    model = {
        "roadmap": SkillRoadmap,
        "issue": RoadmapIssue,
        "comment": IssueComment,
        "checkin": RoadmapCheckin,
    }[kind]
    statement = select(model).where(model.id == target_id)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return await session.scalar(statement)


async def target_route_id(session, kind, target):
    """只解析关联身份，不返回私人学习数据。"""
    if kind == "roadmap":
        return target.id
    if kind == "issue":
        return target.roadmap_id
    if kind == "comment":
        return await session.scalar(
            select(RoadmapIssue.roadmap_id).where(RoadmapIssue.id == target.issue_id)
        )
    return await session.scalar(
        select(UserRoadmap.roadmap_id).where(UserRoadmap.id == target.user_roadmap_id)
    )


async def get_report(session, report_id, *, lock=False):
    """处理时刷新并锁定举报，避免重复结案。"""
    statement = select(ContentReport).where(ContentReport.id == report_id)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return await session.scalar(statement)


async def reports(session, user_id, status, page, page_size):
    """本人列表及管理列表共用分页，权限范围由服务明确传入。"""
    statement = select(ContentReport)
    if user_id is not None:
        statement = statement.where(ContentReport.reporter_id == user_id)
    if status:
        statement = statement.where(ContentReport.status == status)
    total = await session.scalar(select(func.count()).select_from(statement.subquery()))
    rows = list(
        await session.scalars(
            statement.order_by(ContentReport.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return total, rows


async def duplicate_report(session, reporter_id, column, target_id):
    """路线锁保护下，复用本人尚未结案的同目标举报。"""
    return await session.scalar(
        select(ContentReport)
        .where(
            ContentReport.reporter_id == reporter_id,
            column == target_id,
            ContentReport.status.in_(["pending", "processing"]),
        )
        .limit(1)
    )


def add_action(
    session,
    actor_id,
    kind,
    target_id,
    action,
    reason,
    before,
    after,
    report_id=None,
    request_id="internal",
):
    """治理及安全审计随业务事务提交，不复制正文或举报人信息。"""
    session.add(
        ModerationAction(
            actor_id=actor_id,
            report_id=report_id,
            target_type=kind,
            target_id=target_id,
            action=action,
            reason=reason,
            before_state=before,
            after_state=after,
        )
    )
    session.add(
        AuditLog(
            actor_id=actor_id,
            action_code=f"moderation.{kind}.{action}",
            target_type=kind,
            target_id=target_id,
            request_id=request_id,
            result="success",
            details={
                "reportId": str(report_id) if report_id else None,
                "reason": reason,
                "before": before,
                "after": after,
            },
        )
    )
