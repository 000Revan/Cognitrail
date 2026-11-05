"""路线话题事务：路线→账号→话题锁，业务写入与outbox原子提交。"""

from datetime import UTC, datetime, timedelta

from app.core.exceptions import AppError
from app.database.crud import enrollment as learning
from app.database.crud import issue as crud
from app.database.crud import roadmap as roadmaps
from app.database.models import (
    IssueComment,
    IssueEvent,
    IssueSubscription,
    NotificationOutbox,
    RoadmapIssue,
    RoadmapRelease,
    User,
)
from app.domain.roadmap_policy import is_public_route
from app.schemas.common import serialize_utc
from app.services.auth_service import authenticated_account


def now():
    """数据库统一保存无时区UTC。"""
    return datetime.now(UTC).replace(tzinfo=None)


async def accessible_route(session, route_id, user_id, lock=False):
    """公开路线及作者/已有学习者的归档路线可讨论；治理限制始终生效。"""
    route = await roadmaps.get_route(session, route_id, lock=lock)
    release = (
        await session.get(RoadmapRelease, route.current_release_id)
        if route and route.current_release_id
        else None
    )
    author = await roadmaps.get_author(session, route.creator_id) if route else None
    normal = bool(
        route
        and release
        and author
        and route.moderation_status == "normal"
        and release.content_access == "normal"
        and (route.roadmap_type == "official" or author.status == "active")
    )
    allowed = normal and is_public_route(route, release, author)
    if normal and not allowed:
        allowed = route.creator_id == user_id or bool(
            await learning.find_enrollment(session, user_id, route.id)
        )
    if not allowed:
        raise AppError(404, "ROADMAP_NOT_FOUND", "路线不存在或不可访问")
    return route


class IssueService:
    """讨论不创建学习、收藏或进度；受限Markdown保守按纯文本展示。"""

    def __init__(self, session):
        self.session = session

    async def context(self, route_id, claims, lock=False):
        """每次写入重新校验登录状态及路线访问。"""
        route = await accessible_route(self.session, route_id, claims.user_id, lock)
        await authenticated_account(self.session, claims, lock=lock)
        return route

    async def topic(self, route_id, issue_id, lock=False):
        """删除话题保留占位，隐藏话题不可读取。"""
        item = await crud.get_issue(self.session, issue_id, lock)
        if not item or item.roadmap_id != route_id or item.visibility == "hidden":
            raise AppError(404, "ISSUE_NOT_FOUND", "话题不存在或不可访问")
        return item

    async def summary(self, item, viewer, owner):
        """只返回可见正文；删除占位不泄漏原文与作者信息。"""
        visible = item.visibility == "public"
        author = await self.session.get(User, item.author_id) if visible else None
        return {
            "id": str(item.id),
            "roadmapId": str(item.roadmap_id),
            "roadmapCreatorId": str(owner),
            "title": item.title if visible else "话题已删除",
            "body": item.body if visible else None,
            "status": item.status,
            "visibility": item.visibility,
            "author": self.author_summary(author),
            "createdAt": serialize_utc(item.created_at),
            "updatedAt": serialize_utc(item.updated_at),
            "lastActivityAt": serialize_utc(item.last_activity_at),
            "canEdit": visible and item.author_id == viewer,
            "canResolve": visible and viewer == owner,
            "canClose": visible and viewer == owner,
        }

    async def listing(
        self, route_id, claims, status, page, page_size, sort_by="createdAt", order="desc"
    ):
        """登录即可读取，无需先开始学习。"""
        async with self.session.begin():
            route = await self.context(route_id, claims)
            total, rows = await crud.list_issues(
                self.session, route_id, status, page, page_size, sort_by, order
            )
            topic_count, closed_count = await crud.issue_statistics(self.session, route_id)
            counts = await crud.comment_counts(self.session, [r.id for r in rows])
            release = await self.session.get(RoadmapRelease, route.current_release_id)
            return {
                "items": [
                    {
                        **await self.summary(r, claims.user_id, route.creator_id),
                        "commentCount": counts.get(r.id, 0),
                    }
                    for r in rows
                ],
                "topicCount": topic_count,
                "closedCount": closed_count,
                "roadmapTitle": release.title,
                "total": total,
                "page": page,
                "pageSize": page_size,
            }

    @staticmethod
    def author_summary(author):
        """公开身份字段，头像沿用受管路径，不返回登录或私人学习信息。"""
        return (
            {
                "id": str(author.id),
                "username": author.username,
                "nickname": author.nickname,
                "avatarUrl": author.avatar_url,
            }
            if author
            else None
        )

    async def serialize_comments(self, rows, viewer):
        """批量获取回复作者及直接回复对象，保留删除占位。"""
        targets = await crud.reply_targets(self.session, rows)
        authors = await crud.comment_authors(self.session, [*rows, *targets.values()])
        result = []
        for row in rows:
            target = targets.get(row.reply_to_comment_id)
            visible = row.visibility == "public"
            target_visible = target is not None and target.visibility == "public"
            result.append(
                {
                    "id": str(row.id),
                    "body": row.body if visible else None,
                    "visibility": row.visibility,
                    "replyToCommentId": str(row.reply_to_comment_id)
                    if row.reply_to_comment_id
                    else None,
                    "replyToAuthor": self.author_summary(authors.get(target.author_id))
                    if target_visible
                    else None,
                    "author": self.author_summary(authors.get(row.author_id)) if visible else None,
                    "canEdit": visible and row.author_id == viewer,
                    "createdAt": serialize_utc(row.created_at),
                    "updatedAt": serialize_utc(row.updated_at),
                }
            )
        return result

    async def detail(self, route_id, issue_id, claims, page, page_size, anchor=None):
        """根评论分页，楼中楼保留在同组，通知锚点定位根楼层及子回复页。"""
        async with self.session.begin():
            route = await self.context(route_id, claims)
            item = await self.topic(route_id, issue_id)
            if anchor:
                root_id = await crud.root_comment(self.session, issue_id, anchor)
                if root_id is None:
                    raise AppError(404, "COMMENT_NOT_FOUND", "回复锚点不存在")
                preceding = await crud.preceding_comments(self.session, issue_id, root_id)
                page = (preceding - 1) // page_size + 1
            total, roots = await crud.comments(self.session, issue_id, page, page_size)
            if total and not roots and page > 1:
                page = (total - 1) // page_size + 1
                total, roots = await crud.comments(self.session, issue_id, page, page_size)
            groups = await crud.thread_replies(
                self.session, issue_id, [r.id for r in roots], anchor
            )
            all_rows = [*roots, *(r for group in groups.values() for r in group["rows"])]
            serialized = {
                row["id"]: row for row in await self.serialize_comments(all_rows, claims.user_id)
            }
            items = []
            for root in roots:
                group = groups[root.id]
                items.append(
                    {
                        **serialized[str(root.id)],
                        "replies": {
                            "items": [serialized[str(r.id)] for r in group["rows"]],
                            "total": group["total"],
                            "page": group["page"],
                            "pageSize": group["pageSize"],
                        },
                    }
                )
            subscription = await crud.subscription(self.session, issue_id, claims.user_id)
            counts = await crud.comment_counts(self.session, [issue_id])
            release = await self.session.get(RoadmapRelease, route.current_release_id)
            return {
                **await self.summary(item, claims.user_id, route.creator_id),
                "roadmapTitle": release.title,
                "commentCount": counts.get(issue_id, 0),
                "subscribed": bool(subscription and subscription.is_subscribed),
                "comments": {"items": items, "total": total, "page": page, "pageSize": page_size},
                "events": [
                    {
                        "id": str(e.id),
                        "type": e.event_type,
                        "fromStatus": e.from_status,
                        "toStatus": e.to_status,
                        "reason": e.reason,
                        "createdAt": serialize_utc(e.created_at),
                    }
                    for e in await crud.events(self.session, issue_id)
                ],
            }

    async def replies(self, route_id, issue_id, comment_id, claims, page):
        """只读取已授权话题的根评论回复，防止跨话题楼层引用。"""
        async with self.session.begin():
            await self.context(route_id, claims)
            await self.topic(route_id, issue_id)
            root = await crud.get_comment(self.session, issue_id, comment_id)
            if not root or root.reply_to_comment_id is not None:
                raise AppError(404, "COMMENT_NOT_FOUND", "评论不存在")
            group = (
                await crud.thread_replies(self.session, issue_id, [root.id], requested_page=page)
            )[root.id]
            return {
                "items": await self.serialize_comments(group["rows"], claims.user_id),
                "total": group["total"],
                "page": group["page"],
                "pageSize": group["pageSize"],
            }

    async def enqueue(self, item, actor, event_type, key, **extra):
        """与业务记录在同事务落库，payload仅存对象标识。"""
        self.session.add(
            NotificationOutbox(
                event_key=key,
                event_type=event_type,
                payload={
                    "roadmapId": item.roadmap_id,
                    "issueId": item.id,
                    "actorId": actor,
                    **extra,
                },
                available_at=now(),
            )
        )

    async def create(self, route_id, claims, data):
        """默认订阅提问者和作者，同人仅一行。"""
        async with self.session.begin():
            route = await self.context(route_id, claims, True)
            duplicate = await crud.duplicate_issue(
                self.session,
                route_id,
                claims.user_id,
                data.title,
                data.body,
                now() - timedelta(minutes=5),
            )
            if duplicate:
                raise AppError(409, "DUPLICATE_ISSUE", "近期已提交相同话题，请查看已有讨论")
            item = RoadmapIssue(
                roadmap_id=route_id,
                author_id=claims.user_id,
                title=data.title,
                body=data.body,
                status="open",
                visibility="public",
                last_activity_at=now(),
            )
            self.session.add(item)
            await self.session.flush()
            # MySQL不支持INSERT RETURNING，显式异步回读服务端时间，避免隐式IO。
            await self.session.refresh(item)
            for uid in {claims.user_id, route.creator_id}:
                self.session.add(
                    IssueSubscription(
                        issue_id=item.id,
                        user_id=uid,
                        is_subscribed=1,
                        subscription_source="creator" if uid == claims.user_id else "author",
                    )
                )
            self.session.add(
                IssueEvent(
                    issue_id=item.id,
                    actor_id=claims.user_id,
                    event_type="created",
                    to_status="open",
                )
            )
            await self.enqueue(item, claims.user_id, "issue_created", f"issue:{item.id}:created")
            await self.session.flush()
            return await self.summary(item, claims.user_id, route.creator_id)

    async def change(self, route_id, issue_id, claims, action, data=None, comment_id=None):
        """锁话题串行化回复与关闭，状态权限不因管理员身份扩大。"""
        async with self.session.begin():
            route = await self.context(route_id, claims, True)
            item = await self.topic(route_id, issue_id, True)
            if item.visibility != "public":
                raise AppError(409, "ISSUE_DELETED", "话题已删除，仅保留讨论占位")
            stamp = now()
            result = {"id": str(item.id)}
            if action == "subscription":
                row = await crud.subscription(self.session, item.id, claims.user_id)
                if row is None:
                    row = IssueSubscription(
                        issue_id=item.id, user_id=claims.user_id, subscription_source="manual"
                    )
                    self.session.add(row)
                row.is_subscribed = int(data.subscribed)
                row.updated_at = stamp
                result["subscribed"] = data.subscribed
            elif action == "state":
                permitted = claims.user_id == route.creator_id
                if not permitted:
                    raise AppError(
                        403, "ISSUE_STATE_FORBIDDEN", "无权处理此话题状态，请联系路线作者"
                    )
                if item.status != data.expected_status:
                    raise AppError(409, "ISSUE_STATE_CHANGED", "状态已变化，请刷新后重试")
                if item.status == data.status:
                    return {"id": str(item.id), "status": item.status}
                if item.status == "closed" and data.status != "open":
                    raise AppError(409, "ISSUE_CLOSED", "请先重新打开已关闭话题")
                event = IssueEvent(
                    issue_id=item.id,
                    actor_id=claims.user_id,
                    event_type={"open": "reopened", "resolved": "resolved", "closed": "closed"}[
                        data.status
                    ],
                    from_status=item.status,
                    to_status=data.status,
                    reason=data.reason,
                )
                self.session.add(event)
                item.status, item.state_reason, item.state_changed_by = (
                    data.status,
                    data.reason,
                    claims.user_id,
                )
                item.last_activity_at = item.updated_at = stamp
                await self.session.flush()
                await self.enqueue(
                    item, claims.user_id, "issue_state_changed", f"issue-event:{event.id}"
                )
                result["status"] = item.status
            elif action in ("edit", "delete"):
                if item.author_id != claims.user_id:
                    raise AppError(403, "ISSUE_EDIT_FORBIDDEN", "只能编辑或删除本人话题")
                if action == "edit":
                    if serialize_utc(item.updated_at) != data.expected_updated_at:
                        raise AppError(409, "ISSUE_EDIT_CONFLICT", "话题已变化，请刷新")
                    item.title, item.body = data.title, data.body
                    self.session.add(
                        IssueEvent(issue_id=item.id, actor_id=claims.user_id, event_type="edited")
                    )
                else:
                    item.visibility = "deleted"
                item.updated_at = stamp
            elif action == "comment":
                if item.status == "closed":
                    raise AppError(409, "ISSUE_CLOSED", "已关闭话题不能新增回复")
                if data.reply_to_comment_id:
                    target = await crud.get_comment(self.session, item.id, data.reply_to_comment_id)
                    if not target or target.visibility != "public":
                        raise AppError(404, "COMMENT_NOT_FOUND", "回复锚点不存在或不可访问")
                if await crud.duplicate_body(
                    self.session, claims.user_id, item.id, data.body, stamp - timedelta(minutes=5)
                ):
                    raise AppError(409, "DUPLICATE_COMMENT", "近期已提交相同回复，请勿重复发送")
                row = IssueComment(
                    issue_id=item.id,
                    author_id=claims.user_id,
                    body=data.body,
                    reply_to_comment_id=data.reply_to_comment_id,
                    visibility="public",
                )
                self.session.add(row)
                item.last_activity_at = stamp
                await self.session.flush()
                await self.enqueue(
                    item,
                    claims.user_id,
                    "comment_created",
                    f"comment:{row.id}:created",
                    commentId=row.id,
                )
                result["commentId"] = str(row.id)
            elif action in ("edit_comment", "delete_comment"):
                row = await crud.get_comment(self.session, item.id, comment_id)
                if not row or row.visibility != "public":
                    raise AppError(404, "COMMENT_NOT_FOUND", "回复不存在或不可访问")
                if row.author_id != claims.user_id:
                    raise AppError(403, "COMMENT_EDIT_FORBIDDEN", "只能编辑或删除本人回复")
                if action == "edit_comment":
                    if serialize_utc(row.updated_at) != data.expected_updated_at:
                        raise AppError(409, "COMMENT_EDIT_CONFLICT", "回复已变化，请刷新")
                    row.body, row.edited_at = data.body, stamp
                else:
                    row.visibility = "deleted"
                row.updated_at = stamp
            await self.session.flush()
            return result
