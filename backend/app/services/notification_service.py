"""可靠通知与本人消息中心；消息只保存目标ID。"""

import asyncio
import logging
from datetime import timedelta
from uuid import uuid4

from app.core.exceptions import AppError
from app.database.crud import notification as crud
from app.database.models import IssueComment, Notification, RoadmapIssue
from app.schemas.common import serialize_utc
from app.services.auth_service import authenticated_account
from app.services.issue_service import accessible_route, now

logger = logging.getLogger(__name__)


class OutboxDispatcher:
    """短事务领取，插入与确认分开；崩溃窗口依靠唯一键恢复。"""

    def __init__(self, database, settings):
        self.database, self.settings = database, settings

    async def claim(self):
        """每次只领一个任务，不让排队处理消耗租期。"""
        async with self.database.sessions() as session, session.begin():
            stamp = now()
            row = await crud.claimable(session, stamp)
            if not row:
                return None
            row.status, row.lease_token = "processing", str(uuid4())
            row.lease_until = stamp + timedelta(seconds=self.settings.outbox_lease_seconds)
            row.attempts += 1
            row.updated_at = stamp
            return row.id, row.lease_token

    @staticmethod
    def owns(row, token):
        """过期worker即使还持旧token也不能投递或确认。"""
        return bool(
            row
            and row.status == "processing"
            and row.lease_token == token
            and row.lease_until
            and row.lease_until > now()
        )

    async def deliver(self, task_id, token):
        """锁定租约后校验订阅、禁用账号和目标；去重后插入通知。"""
        async with self.database.sessions() as session, session.begin():
            row = await crud.leased(session, task_id)
            if not self.owns(row, token):
                return False
            payload = row.payload
            rid, actor = int(payload["roadmapId"]), int(payload["actorId"])
            iid = int(payload["issueId"]) if payload.get("issueId") else None
            cid = int(payload["commentId"]) if payload.get("commentId") else None
            release = int(payload["releaseId"]) if payload.get("releaseId") else None
            recipients = set()
            if row.event_type == "release_published":
                recipients = await crud.subscribers(session, route_id=rid)
            elif row.event_type in ("issue_created", "comment_created", "issue_state_changed"):
                topic = await session.get(RoadmapIssue, iid)
                if not topic or topic.roadmap_id != rid or topic.visibility != "public":
                    return True
                recipients = await crud.subscribers(session, topic_id=iid)
                if row.event_type == "comment_created":
                    comment = await session.get(IssueComment, cid)
                    if not comment or comment.issue_id != iid or comment.visibility != "public":
                        return True
                    if comment.reply_to_comment_id:
                        target = await session.get(IssueComment, comment.reply_to_comment_id)
                        if target:
                            recipients.add(target.author_id)
                elif row.event_type == "issue_created":
                    # 新话题只提醒路线作者，作者本人发帖不自通知。
                    from app.database.models import SkillRoadmap

                    route = await session.get(SkillRoadmap, rid)
                    recipients &= {route.creator_id} if route else set()
            else:
                raise ValueError("unsupported outbox event")
            recipients.discard(actor)
            active = await crud.active_recipients(session, recipients)
            for uid in sorted(active):
                try:
                    await accessible_route(session, rid, uid)
                except AppError as exc:
                    if exc.status_code == 404:
                        continue
                    raise
                await crud.put_notification(
                    session,
                    recipient_id=uid,
                    actor_id=actor,
                    notification_type=row.event_type,
                    event_key=row.event_key,
                    roadmap_id=rid,
                    issue_id=iid,
                    comment_id=cid,
                    release_id=release,
                )
            # 处理超过租期时整批回滚；旧worker不能在过期后提交通知。
            if not self.owns(row, token):
                raise RuntimeError("outbox lease expired during delivery")
            return True

    async def acknowledge(self, task_id, token):
        """仅租约持有人确认；投递后崩溃则重领并幂等插入。"""
        async with self.database.sessions() as session, session.begin():
            row = await crud.leased(session, task_id)
            if not self.owns(row, token):
                return False
            row.status, row.lease_token, row.lease_until = "done", None, None
            row.last_error, row.updated_at = None, now()
            return True

    async def retry(self, task_id, token, error):
        """只记录异常类名，避免payload、SQL参数或连接凭证进入错误摘要。"""
        async with self.database.sessions() as session, session.begin():
            row = await crud.leased(session, task_id)
            if not self.owns(row, token):
                return
            row.status = (
                "failed" if row.attempts >= self.settings.outbox_max_attempts else "pending"
            )
            row.available_at = now() + timedelta(seconds=min(300, 2 ** min(row.attempts, 8)))
            row.lease_token, row.lease_until = None, None
            row.last_error, row.updated_at = type(error).__name__, now()

    async def run_once(self):
        """单任务失败不影响HTTP服务；断库时由外层循环退避。"""
        task = await self.claim()
        if task is None:
            return False
        try:
            if await self.deliver(*task):
                await self.acknowledge(*task)
        except Exception as exc:
            await self.retry(*task, exc)
        return True

    async def run(self):
        """应用后台轮询，取消时退出，不隐式建表。"""
        while True:
            try:
                worked = await self.run_once()
            except Exception as exc:
                logger.warning("outbox_poll_failed error_type=%s", type(exc).__name__)
                worked = False
            await asyncio.sleep(0.05 if worked else self.settings.outbox_poll_seconds)


class NotificationService:
    """本人未读计数、已读及重新授权目标；不返回讨论正文。"""

    def __init__(self, session):
        self.session = session

    async def listing(self, claims, page, page_size, unread=False):
        """受限通知仍显示通用记录，但不返回原路线标题或正文。"""
        async with self.session.begin():
            await authenticated_account(self.session, claims)
            total, rows = await crud.notification_rows(
                self.session, claims.user_id, page, page_size, unread
            )
            if not total:
                page = 1
            if total and not rows and page > 1:
                page = (total - 1) // page_size + 1
                total, rows = await crud.notification_rows(
                    self.session, claims.user_id, page, page_size, unread
                )
            latest_id = await crud.latest_notification_id(self.session, claims.user_id)
            return {
                "latestId": str(latest_id) if latest_id is not None else None,
                "items": [
                    {
                        "id": str(r.id),
                        "type": r.notification_type,
                        "readAt": serialize_utc(r.read_at) if r.read_at else None,
                        "createdAt": serialize_utc(r.created_at),
                    }
                    for r in rows
                ],
                "total": total,
                "page": page,
                "pageSize": page_size,
            }

    async def unread(self, claims):
        """仅统计本人的未读消息。"""
        async with self.session.begin():
            await authenticated_account(self.session, claims)
            count = await crud.unread_count(self.session, claims.user_id)
            return {"count": count}

    async def read(self, claims, notification_id=None, through_id=None):
        """单条或列表边界内批量已读，新到达消息保持未读。"""
        async with self.session.begin():
            await authenticated_account(self.session, claims, lock=True)
            if notification_id:
                row = await self.session.get(Notification, notification_id)
                if not row or row.recipient_id != claims.user_id or row.deleted_at is not None:
                    raise AppError(404, "NOTIFICATION_NOT_FOUND", "通知不存在")
            await crud.mark_read(self.session, claims.user_id, now(), notification_id, through_id)
            return {"read": True}

    async def delete(self, claims, notification_id=None, through_id=None, read_only=False):
        """本人收件箱清理不依赖目标仍可访问，不删除话题或评论。"""
        async with self.session.begin():
            await authenticated_account(self.session, claims, lock=True)
            if notification_id:
                row = await self.session.get(Notification, notification_id)
                if not row or row.recipient_id != claims.user_id:
                    raise AppError(404, "NOTIFICATION_NOT_FOUND", "通知不存在")
            count = await crud.remove_notifications(
                self.session, claims.user_id, now(), notification_id, through_id, read_only
            )
            return {"deletedCount": count}

    async def target(self, claims, notification_id):
        """点击重新授权；被删除/隐藏的回复定位占位，受限话题不返回可跳转地址。"""
        async with self.session.begin():
            await authenticated_account(self.session, claims)
            row = await self.session.get(Notification, notification_id)
            if not row or row.recipient_id != claims.user_id or row.deleted_at is not None:
                raise AppError(404, "NOTIFICATION_NOT_FOUND", "通知不存在")
            try:
                await accessible_route(self.session, row.roadmap_id, claims.user_id)
                if row.issue_id:
                    topic = await self.session.get(RoadmapIssue, row.issue_id)
                    if (
                        not topic
                        or topic.visibility == "hidden"
                        or topic.roadmap_id != row.roadmap_id
                    ):
                        raise AppError(404, "ISSUE_NOT_FOUND", "话题不可访问")
                if row.comment_id:
                    comment = await self.session.get(IssueComment, row.comment_id)
                    if (
                        not comment
                        or comment.visibility != "public"
                        or comment.issue_id != row.issue_id
                    ):
                        raise AppError(404, "COMMENT_NOT_FOUND", "评论已删除或不可访问")
            except AppError as exc:
                if exc.status_code != 404:
                    raise
                return {"accessible": False, "path": None, "message": "目标内容已受限或不可访问"}
            path = f"/roadmaps/{row.roadmap_id}"
            if row.issue_id:
                path += f"/issues/{row.issue_id}"
                if row.comment_id:
                    path += f"?commentId={row.comment_id}#comment-{row.comment_id}"
            return {"accessible": True, "path": path, "message": None}
