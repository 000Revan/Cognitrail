"""R05 学习事务：路线→账号→关系→当前会话，冻结内容只读。"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.exceptions import AppError
from app.database.crud import enrollment as crud
from app.database.crud import roadmap as roadmaps
from app.database.crud import user as social
from app.database.crud.favorite import release_counts
from app.database.models import (
    LearningSession,
    LearningSessionEvent,
    ReleaseResource,
    ResourceVisit,
    RoadmapCheckin,
    RoadmapRelease,
    UserNodeProgress,
    UserRoadmap,
)
from app.domain.roadmap_policy import is_public_route, learning_upgrade_plan
from app.schemas.common import serialize_utc
from app.services.auth_service import authenticated_account


def now():
    """数据库统一保存无时区 UTC，业务日期单独按北京时间计算。"""
    return datetime.now(UTC).replace(tzinfo=None)


def timestamp(value):
    return serialize_utc(value) if value is not None else None


def day_statistics(values, today):
    """同日多路线只计一天；今天未打卡时允许从昨天延续连续天数。"""
    days = sorted(set(d for d in values if d <= today))
    longest = run = 0
    previous = None
    for day in days:
        run = run + 1 if previous and day == previous + timedelta(days=1) else 1
        longest = max(longest, run)
        previous = day
    dates = set(days)
    cursor = today if today in dates else today - timedelta(days=1)
    current = 0
    while cursor in dates:
        current += 1
        cursor -= timedelta(days=1)
    return len(days), current, longest


class EnrollmentService:
    """本人学习服务；开始、恢复、完成与打卡均由用户主动执行。"""

    def __init__(self, session, timezone="Asia/Shanghai"):
        self.session = session
        # R05 固定业务日期口径，不能由调用者或客户端改变。
        self.timezone = ZoneInfo("Asia/Shanghai")

    async def upgrade_snapshot(self, release_id, *, lock=False):
        """归一冻结图用于差异比较，排除每次发布重新分配的快照ID。"""
        stages, nodes, resources, edges = await crud.release_graph(
            self.session, release_id, lock=lock
        )
        stages.sort(key=lambda s: (s.position, s.id))
        stage_map = {s.id: s for s in stages}
        nodes.sort(key=lambda n: (stage_map[n.stage_id].position, n.position, n.id))
        normalized = []
        for node in nodes:
            stage = stage_map[node.stage_id]
            normalized.append(
                {
                    "id": node.id,
                    "stableKey": node.stable_key,
                    "revisionNo": node.revision_no,
                    "stageKey": stage.stable_key,
                    "stageTitle": stage.title,
                    "position": node.position,
                    "title": node.title,
                    "content": node.content,
                    "tips": node.tips,
                    "estimatedMinutes": node.estimated_minutes,
                    "isOptional": bool(node.is_optional),
                    "countsTowardProgress": bool(node.counts_toward_progress),
                    "canvasX": node.canvas_x,
                    "canvasY": node.canvas_y,
                    "resources": [
                        (
                            r.position,
                            r.title,
                            r.resource_type,
                            r.url,
                            r.language_code,
                            r.access_type,
                        )
                        for r in sorted(resources, key=lambda r: (r.position, r.id))
                        if r.node_id == node.id
                    ],
                }
            )
        return {
            "nodes": normalized,
            "stages": {s.stable_key: s for s in stages},
            "edges": {
                (stage_map[e.source_stage_id].stable_key, stage_map[e.target_stage_id].stable_key)
                for e in edges
            },
        }

    async def upgrade_target(self, relation, route, learning, source_release, *, lock=False):
        """只向当前最新公开且可访问版本升级，归档、退出、受限与降级都拒绝。"""
        self.require_writable(relation, route, learning, source_release, learning.id)
        target = await crud.get_release(self.session, route.current_release_id, lock=lock)
        author = await roadmaps.get_author(self.session, route.creator_id)
        if not is_public_route(route, target, author):
            raise AppError(
                409, "UPGRADE_TARGET_UNAVAILABLE", "最新版暂不可学习，请继续当前版本或稍后重试"
            )
        if target.version_no <= source_release.version_no:
            raise AppError(409, "UPGRADE_NOT_AVAILABLE", "当前已是最新可用学习版本")
        return target

    async def upgrade_material(self, learning, target, confirmations, *, lock=False):
        """只读取当前源会话完成事实，不遍历任意历史来找回已删除任务。"""
        source = await self.upgrade_snapshot(learning.release_id, lock=lock)
        destination = await self.upgrade_snapshot(target.id, lock=lock)
        progress = await crud.progress_rows(self.session, learning.id, lock=lock)
        source_keys = {n["id"]: n["stableKey"] for n in source["nodes"]}
        completed = {source_keys[p.release_node_id]: p for p in progress if p.is_completed}
        plan = learning_upgrade_plan(
            source["nodes"],
            destination["nodes"],
            set(completed),
            source_keys.get(learning.last_node_id),
            confirmations,
        )
        return source, destination, completed, plan

    async def upgrade_preview(self, enrollment_id, claims):
        """预览只读差异与影响，不创建新会话、完成或打卡。"""
        async with self.session.begin():
            relation, route, learning, source_release = await self.context(enrollment_id, claims)
            target = await self.upgrade_target(relation, route, learning, source_release)
            source, destination, _, plan = await self.upgrade_material(learning, target, {})
            stage_changes = []
            for key in [
                *destination["stages"],
                *(k for k in source["stages"] if k not in destination["stages"]),
            ]:
                before, after = source["stages"].get(key), destination["stages"].get(key)
                changes = (
                    ["added"]
                    if before is None
                    else ["removed"]
                    if after is None
                    else [
                        field
                        for field in ("title", "description", "position", "canvas_x", "canvas_y")
                        if getattr(before, field) != getattr(after, field)
                    ]
                )
                if changes:
                    stage_changes.append(
                        {
                            "stableKey": key,
                            "sourceTitle": before.title if before else None,
                            "targetTitle": after.title if after else None,
                            "changes": changes,
                        }
                    )
            total = plan["targetTotal"]
            return {
                "sourceSessionId": str(learning.id),
                "targetReleaseId": str(target.id),
                "sourceVersionNo": source_release.version_no,
                "targetVersionNo": target.version_no,
                "progressVersion": learning.progress_version,
                "updateSummary": target.update_summary,
                "sourceCompleted": plan["sourceCompleted"],
                "sourceTotal": plan["sourceTotal"],
                "sourcePercent": plan["sourceCompleted"] * 100 // plan["sourceTotal"]
                if plan["sourceTotal"]
                else 0,
                "targetTotal": total,
                "completedMin": plan["completedMin"],
                "completedMax": plan["completedMax"],
                "percentMin": plan["completedMin"] * 100 // total if total else 0,
                "percentMax": plan["completedMax"] * 100 // total if total else 0,
                "nodeChanges": plan["nodeChanges"],
                "stageChanges": stage_changes,
                "connectionsChanged": source["edges"] != destination["edges"],
                "releaseChanges": [
                    field
                    for field in (
                        "title",
                        "summary",
                        "difficulty",
                        "effort_note",
                        "license_code",
                        "license_url",
                    )
                    if getattr(source_release, field) != getattr(target, field)
                ],
            }

    @staticmethod
    def upgrade_request_data(data):
        """排序后的规范语义用于请求键重放，选择的展示顺序不影响请求含义。"""
        return {
            "sourceSessionId": str(data.source_session_id),
            "targetReleaseId": str(data.target_release_id),
            "progressVersion": data.progress_version,
            "confirmations": sorted(
                [{"stableKey": str(c.stable_key), "action": c.action} for c in data.confirmations],
                key=lambda c: c["stableKey"],
            ),
        }

    async def upgrade(self, enrollment_id, claims, data):
        """锁关系与源会话后重验预览，目标会话、迁移、事件与指针同事务提交。"""
        async with self.session.begin():
            relation, route, learning, source_release = await self.context(
                enrollment_id, claims, write=True
            )
            request = self.upgrade_request_data(data)
            event = await crud.event_by_key(self.session, relation.id, str(data.request_key))
            if event:
                if (
                    event.event_type != "upgrade"
                    or not event.details
                    or event.details.get("request") != request
                ):
                    raise AppError(
                        409, "UPGRADE_REQUEST_CONFLICT", "同一升级请求键不能使用不同参数"
                    )
                receipt_release = await crud.get_release(
                    self.session, data.target_release_id, lock=True
                )
                if not self.available(route, receipt_release):
                    raise AppError(409, "ROADMAP_DISABLED", "升级记录仍保留，但内容已受限")
                return event.details["result"]
            self.require_writable(relation, route, learning, source_release, data.source_session_id)
            if learning.progress_version != data.progress_version:
                raise AppError(
                    409, "UPGRADE_PREVIEW_EXPIRED", "学习位置或进度已变化，请重新查看差异"
                )
            target = await self.upgrade_target(relation, route, learning, source_release, lock=True)
            if target.id != data.target_release_id:
                raise AppError(409, "UPGRADE_PREVIEW_EXPIRED", "作者已发布更新版本，请重新查看差异")
            choices = {str(c.stable_key): c.action for c in data.confirmations}
            _, destination, completed, plan = await self.upgrade_material(
                learning, target, choices, lock=True
            )
            if set(choices) != plan["requiredKeys"]:
                raise AppError(
                    422,
                    "UPGRADE_CONFIRMATIONS_REQUIRED",
                    "请为全部需确认节点选择保留完成或重新学习，不得确认其他节点",
                )
            instant = now()
            node_map = {node["stableKey"]: node for node in destination["nodes"]}
            new_session = LearningSession(
                user_roadmap_id=relation.id,
                roadmap_id=route.id,
                release_id=target.id,
                source_session_id=learning.id,
                started_at=instant,
                last_node_id=node_map[plan["lastNodeKey"]]["id"] if plan["lastNodeKey"] else None,
                last_opened_at=instant,
                progress_version=1,
                updated_at=instant,
                first_completed_at=instant
                if plan["targetTotal"] and plan["completedCount"] == plan["targetTotal"]
                else None,
            )
            self.session.add(new_session)
            await self.session.flush()
            await self.inherit_resource_visits(learning, new_session)
            for key in sorted(plan["completedKeys"]):
                original = completed[key]
                self.session.add(
                    UserNodeProgress(
                        session_id=new_session.id,
                        release_id=target.id,
                        release_node_id=node_map[key]["id"],
                        is_completed=1,
                        completed_at=original.completed_at,
                        completion_source="confirmed"
                        if key in plan["requiredKeys"]
                        else "migrated",
                        source_progress_id=original.id,
                        updated_at=instant,
                    )
                )
            await self.session.flush()
            result = {
                "sourceSessionId": str(learning.id),
                "targetSessionId": str(new_session.id),
                "targetReleaseId": str(target.id),
                "versionNo": target.version_no,
                "progressVersion": 1,
                "completedNodeCount": plan["completedCount"],
                "progressNodeCount": plan["targetTotal"],
                "progressPercent": plan["completedCount"] * 100 // plan["targetTotal"]
                if plan["targetTotal"]
                else 0,
                "lastNodeId": str(new_session.last_node_id) if new_session.last_node_id else None,
            }
            self.session.add(
                LearningSessionEvent(
                    user_roadmap_id=relation.id,
                    actor_id=claims.user_id,
                    event_type="upgrade",
                    from_session_id=learning.id,
                    to_session_id=new_session.id,
                    request_key=str(data.request_key),
                    details={"request": request, "result": result},
                )
            )
            await self.session.flush()
            relation.current_session_id = new_session.id
            relation.dismissed_release_id = None
            relation.updated_at = instant
            await self.session.flush()
            return result

    async def sessions(self, enrollment_id, claims, page, page_size):
        """列出本人绑定过的版本，只读回顾不改变当前学习关系或位置。"""
        async with self.session.begin():
            relation, route, _, _ = await self.context(enrollment_id, claims)
            total, rows = await crud.session_rows(self.session, relation.id, page, page_size)
            return {
                "items": [
                    await self.summary(relation, route, learning, release)
                    for learning, release in rows
                ],
                "total": total,
                "page": page,
                "pageSize": page_size,
            }

    def today(self):
        return now().replace(tzinfo=UTC).astimezone(self.timezone).date()

    async def context(self, enrollment_id, claims, *, write=False, session_id=None):
        """先限定归属，写入按固定锁顺序复核身份、治理状态和当前会话。"""
        relation = await crud.get_enrollment(self.session, enrollment_id, claims.user_id)
        if relation is None:
            raise AppError(404, "ENROLLMENT_NOT_FOUND", "学习关系不存在或不可访问")
        route = await roadmaps.get_route(self.session, relation.roadmap_id, lock=write)
        await authenticated_account(self.session, claims, lock=write)
        if write:
            relation = await crud.get_enrollment(
                self.session, enrollment_id, claims.user_id, lock=True
            )
        learning = await crud.get_session(self.session, relation, lock=write)
        if learning is None:
            raise AppError(409, "LEARNING_SESSION_MISSING", "学习会话未就绪，请刷新后重试")
        if not write and session_id is not None and learning.id != session_id:
            learning = await crud.get_session_by_id(self.session, relation.id, session_id)
            if learning is None:
                raise AppError(404, "LEARNING_SESSION_NOT_FOUND", "学习版本不存在或不可访问")
        release = await crud.get_release(self.session, learning.release_id, lock=write)
        return relation, route, learning, release

    @staticmethod
    def available(route, release):
        """作者归档不影响已加入版本；平台及发布版访问限制阻断正文与新增写入。"""
        return route.moderation_status == "normal" and release.content_access == "normal"

    def require_writable(self, relation, route, learning, release, session_id):
        if session_id != learning.id:
            raise AppError(409, "LEARNING_SESSION_CHANGED", "学习版本已变化，请刷新后继续")
        if not self.available(route, release):
            raise AppError(409, "ROADMAP_DISABLED", "内容已下架，正文与新增学习操作不可用")
        if relation.status != "active":
            raise AppError(409, "ENROLLMENT_ABANDONED", "已退出学习，请先恢复原版学习")

    async def summary(self, relation, route, learning, release, *, lock=False):
        """摘要只取本人绑定快照，受限内容不返回标题、简介或目录数量。"""
        available = self.available(route, release)
        current = (
            await self.session.get(RoadmapRelease, route.current_release_id)
            if route.current_release_id
            else None
        )
        author = await roadmaps.get_author(self.session, route.creator_id)
        public = is_public_route(route, current, author)
        stages, nodes = await release_counts(self.session, [release.id])
        completed, total = await crud.progress_counts(self.session, learning, lock=lock)
        return {
            "id": str(relation.id),
            "roadmapId": str(route.id),
            "sessionId": str(learning.id),
            "releaseId": str(release.id),
            "versionNo": release.version_no,
            "title": release.title if available else "内容已下架",
            "description": release.summary if available else None,
            "difficulty": release.difficulty if available else None,
            "status": relation.status,
            "startedAt": timestamp(relation.started_at),
            "abandonedAt": timestamp(relation.abandoned_at),
            "completedAt": timestamp(learning.first_completed_at),
            "lastNodeId": str(learning.last_node_id)
            if available and learning.last_node_id
            else None,
            "lastOpenedAt": timestamp(learning.last_opened_at),
            "progressVersion": learning.progress_version,
            "contentAvailable": available,
            "writable": available
            and relation.status == "active"
            and learning.id == relation.current_session_id,
            "isCurrentSession": learning.id == relation.current_session_id,
            "hasNewVersion": bool(public and current.version_no > release.version_no),
            "updatePromptDismissed": bool(public and relation.dismissed_release_id == current.id),
            "currentVersionNo": current.version_no if public else None,
            "currentReleaseId": str(current.id) if public else None,
            "stageCount": stages.get(release.id, 0) if available else 0,
            "nodeCount": nodes.get(release.id, 0) if available else 0,
            "completedNodeCount": completed,
            "progressNodeCount": total,
            "progressPercent": completed * 100 // total if total else 0,
        }

    def event(self, relation, learning, claims, event_type):
        """仅保存加入、退出、恢复必要事件，不生成节点浏览日志。"""
        self.session.add(
            LearningSessionEvent(
                user_roadmap_id=relation.id,
                actor_id=claims.user_id,
                event_type=event_type,
                request_key=str(uuid4()),
                from_session_id=learning.id if event_type == "abandon" else None,
                to_session_id=None if event_type == "abandon" else learning.id,
            )
        )

    async def enroll(self, route_id, claims, release_id):
        """同事务建立单关系与首会话；路线锁使并发首次开始复用同一结果。"""
        async with self.session.begin():
            route = await roadmaps.get_route(self.session, route_id, lock=True)
            await authenticated_account(self.session, claims, lock=True)
            if route is None:
                raise AppError(404, "ROADMAP_NOT_FOUND", "路线不存在或不可访问")
            if route.creator_id == claims.user_id:
                raise AppError(
                    403, "SELF_ENROLLMENT_FORBIDDEN", "不能学习本人创作的路线，请预览工作稿"
                )
            relation = await crud.find_enrollment(self.session, claims.user_id, route_id, lock=True)
            if relation:
                learning = await crud.get_session(self.session, relation, lock=True)
                release = await self.session.get(RoadmapRelease, learning.release_id)
                # 已有关系始终复用原版，禁止以再次开始代替升级或重置。
                if release_id not in (learning.release_id, route.current_release_id):
                    raise AppError(409, "RELEASE_CHANGED", "发布版本已变化，请刷新详情")
                return await self.summary(relation, route, learning, release, lock=True)
            release = (
                await self.session.get(RoadmapRelease, route.current_release_id)
                if route.current_release_id
                else None
            )
            author = await roadmaps.get_author(self.session, route.creator_id)
            if not is_public_route(route, release, author):
                raise AppError(404, "ROADMAP_NOT_FOUND", "路线不存在或不可访问")
            if release_id != release.id:
                raise AppError(409, "RELEASE_CHANGED", "发布版本已变化，请刷新详情后开始")
            _, stages, nodes, _ = await roadmaps.release_rows(self.session, release.id)
            first_node = next((n for s in stages for n in nodes if n.stage_id == s.id), None)
            instant = now()
            relation = UserRoadmap(
                user_id=claims.user_id,
                roadmap_id=route_id,
                status="active",
                started_at=instant,
                updated_at=instant,
            )
            self.session.add(relation)
            await self.session.flush()
            learning = LearningSession(
                user_roadmap_id=relation.id,
                roadmap_id=route_id,
                release_id=release.id,
                started_at=instant,
                last_node_id=first_node.id if first_node else None,
                last_opened_at=instant,
                progress_version=1,
                updated_at=instant,
            )
            self.session.add(learning)
            await self.session.flush()
            relation.current_session_id = learning.id
            self.event(relation, learning, claims, "join")
            await social.record_activity(
                self.session,
                claims.user_id,
                route_id,
                "learning",
                f"learning:{uuid4()}",
                self.today(),
            )
            await self.session.flush()
            return await self.summary(relation, route, learning, release, lock=True)

    async def detail(self, enrollment_id, claims, session_id=None):
        async with self.session.begin():
            return await self.summary(
                *await self.context(enrollment_id, claims, session_id=session_id)
            )

    async def listing(self, current, status, page, page_size):
        async with self.session.begin():
            await authenticated_account(self.session, current.claims)
            total, rows = await crud.enrollment_rows(
                self.session, current.user.id, status, page, page_size
            )
            return {
                "items": [await self.summary(*row) for row in rows],
                "total": total,
                "page": page,
                "pageSize": page_size,
            }

    @staticmethod
    def progress_data(progress):
        return {
            "releaseNodeId": str(progress.release_node_id),
            "completed": bool(progress.is_completed),
            "completedAt": timestamp(progress.completed_at),
        }

    async def content(self, enrollment_id, claims, session_id=None):
        """在读取节点正文和资源前校验本人及当前绑定版访问权限。"""
        async with self.session.begin():
            relation, route, learning, release = await self.context(
                enrollment_id, claims, session_id=session_id
            )
            if not self.available(route, release):
                raise AppError(409, "ROADMAP_DISABLED", "内容已下架，正文与资源不可访问")
            _, stages, nodes, resources = await roadmaps.release_rows(self.session, release.id)
            edges = await roadmaps.release_edges(self.session, release.id)
            tree = [
                {
                    "id": str(s.id),
                    "title": s.title,
                    "description": s.description,
                    "canvasX": float(s.canvas_x),
                    "canvasY": float(s.canvas_y),
                    "nodes": [
                        {
                            "id": str(n.id),
                            "title": n.title,
                            "content": n.content,
                            "estimatedMinutes": n.estimated_minutes,
                            "tips": n.tips,
                            "isOptional": bool(n.is_optional),
                            "countsTowardProgress": bool(n.counts_toward_progress),
                            "canvasX": float(n.canvas_x),
                            "canvasY": float(n.canvas_y),
                            "resources": [
                                {
                                    "id": str(r.id),
                                    "title": r.title,
                                    "resourceType": r.resource_type,
                                    "resourceUrl": r.url,
                                    "languageCode": r.language_code,
                                    "accessType": r.access_type,
                                }
                                for r in resources
                                if r.node_id == n.id
                            ],
                        }
                        for n in nodes
                        if n.stage_id == s.id
                    ],
                }
                for s in stages
            ]
            return {
                "enrollment": await self.summary(relation, route, learning, release),
                "stages": tree,
                "connections": [
                    {"source": str(e.source_stage_id), "target": str(e.target_stage_id)}
                    for e in edges
                ],
                "visitedResourceIds": [
                    str(v.release_resource_id) for v in await self.resource_visits(learning.id)
                ],
                "progress": [
                    self.progress_data(p)
                    for p in await crud.progress_rows(self.session, learning.id)
                ],
            }

    async def resource_visits(self, session_id, *, lock=False):
        statement = select(ResourceVisit).where(ResourceVisit.session_id == session_id)
        return list(await self.session.scalars(crud.current_read(statement, lock)))

    async def visit_resource(self, enrollment_id, resource_id, claims, data):
        async with self.session.begin():
            relation, route, learning, release = await self.context(
                enrollment_id, claims, write=True
            )
            self.require_writable(relation, route, learning, release, data.session_id)
            resource = await self.session.scalar(
                select(ReleaseResource.id).where(
                    ReleaseResource.id == resource_id, ReleaseResource.release_id == release.id
                )
            )
            if resource is None:
                raise AppError(404, "RELEASE_RESOURCE_NOT_FOUND", "资源不属于当前学习版本")
            visit = await self.session.get(
                ResourceVisit, (learning.id, resource_id), with_for_update=True
            )
            instant = now()
            if visit is None:
                self.session.add(
                    ResourceVisit(
                        session_id=learning.id,
                        release_resource_id=resource_id,
                        release_id=release.id,
                        first_visited_at=instant,
                        last_visited_at=instant,
                    )
                )
            else:
                visit.last_visited_at = max(instant, visit.last_visited_at)
            return {"resourceId": str(resource_id)}

    async def inherit_resource_visits(self, source, destination):
        visits = {
            v.release_resource_id: v for v in await self.resource_visits(source.id, lock=True)
        }
        if not visits:
            return

        def resource_key(resource, nodes):
            return (
                nodes[resource.node_id],
                resource.url,
                resource.title,
                resource.resource_type,
                resource.language_code,
                resource.access_type,
                resource.position,
            )

        _, nodes, resources, _ = await crud.release_graph(
            self.session, source.release_id, lock=True
        )
        keys = {n.id: n.stable_key for n in nodes}
        matches = {resource_key(r, keys): visits[r.id] for r in resources if r.id in visits}
        _, nodes, resources, _ = await crud.release_graph(
            self.session, destination.release_id, lock=True
        )
        keys = {n.id: n.stable_key for n in nodes}
        for resource in resources:
            visit = matches.get(resource_key(resource, keys))
            if visit:
                self.session.add(
                    ResourceVisit(
                        session_id=destination.id,
                        release_resource_id=resource.id,
                        release_id=destination.release_id,
                        first_visited_at=visit.first_visited_at,
                        last_visited_at=visit.last_visited_at,
                    )
                )

    async def position(self, enrollment_id, claims, data):
        """保存阅读位置，不创建进度、打卡或打开外部资源。"""
        async with self.session.begin():
            relation, route, learning, release = await self.context(
                enrollment_id, claims, write=True
            )
            self.require_writable(relation, route, learning, release, data.session_id)
            if await crud.get_node(self.session, release.id, data.node_id) is None:
                raise AppError(404, "RELEASE_NODE_NOT_FOUND", "节点不属于当前学习版本")
            instant = now()
            if learning.last_node_id != data.node_id:
                learning.progress_version += 1
            learning.last_node_id = data.node_id
            learning.last_opened_at = instant
            learning.updated_at = instant
            await self.session.flush()
            return await self.summary(relation, route, learning, release, lock=True)

    async def update_node(self, enrollment_id, node_id, claims, data):
        """同版节点完成或撤销；幂等重放不改变完成时间与进度版本。"""
        async with self.session.begin():
            relation, route, learning, release = await self.context(
                enrollment_id, claims, write=True
            )
            self.require_writable(relation, route, learning, release, data.session_id)
            if await crud.get_node(self.session, release.id, node_id) is None:
                raise AppError(404, "RELEASE_NODE_NOT_FOUND", "节点不属于当前学习版本")
            progress = await crud.get_progress(self.session, learning.id, node_id)
            if bool(progress and progress.is_completed) != data.completed:
                instant = now()
                if progress is None:
                    progress = UserNodeProgress(
                        session_id=learning.id,
                        release_id=release.id,
                        release_node_id=node_id,
                        completion_source="manual",
                    )
                    self.session.add(progress)
                progress.is_completed = int(data.completed)
                progress.completed_at = instant if data.completed else None
                progress.updated_at = instant
                learning.progress_version += 1
                learning.updated_at = instant
                await self.session.flush()
                completed, total = await crud.progress_counts(self.session, learning, lock=True)
                if total and completed == total and learning.first_completed_at is None:
                    learning.first_completed_at = instant
            await self.session.flush()
            return await self.summary(relation, route, learning, release, lock=True)

    async def transition(self, enrollment_id, claims, action, data):
        """退出保留全部历史，恢复始终使用原当前会话与位置。"""
        async with self.session.begin():
            relation, route, learning, release = await self.context(
                enrollment_id, claims, write=True
            )
            if data.session_id != learning.id:
                raise AppError(409, "LEARNING_SESSION_CHANGED", "学习版本已变化，请刷新")
            if action == "restore" and not self.available(route, release):
                raise AppError(409, "ROADMAP_DISABLED", "内容已下架，无法恢复学习")
            target = "abandoned" if action == "abandon" else "active"
            if relation.status != target:
                relation.status = target
                relation.abandoned_at = now() if target == "abandoned" else None
                relation.updated_at = now()
                self.event(
                    relation, learning, claims, "abandon" if target == "abandoned" else "resume"
                )
                if target == "abandoned":
                    await social.deactivate_activity(
                        self.session, claims.user_id, route.id, "learning"
                    )
                else:
                    await social.record_activity(
                        self.session,
                        claims.user_id,
                        route.id,
                        "learning",
                        f"learning:{uuid4()}",
                        self.today(),
                    )
            await self.session.flush()
            return await self.summary(relation, route, learning, release, lock=True)

    @staticmethod
    def record_data(record):
        return {
            "id": str(record.id),
            "sessionId": str(record.session_id),
            "checkinDate": record.checkin_date.isoformat(),
            "timezoneName": record.timezone_name,
            "isValid": bool(record.is_valid),
            "createdAt": timestamp(record.created_at),
        }

    async def create_record(self, enrollment_id, claims, data):
        """关系锁与唯一约束保证同日一次，已撤销记录仍占用当天资格。"""
        async with self.session.begin():
            relation, route, learning, release = await self.context(
                enrollment_id, claims, write=True
            )
            self.require_writable(relation, route, learning, release, data.session_id)
            today = self.today()
            record = await crud.record_for_day(self.session, relation.id, today)
            if record is None:
                record = RoadmapCheckin(
                    user_roadmap_id=relation.id,
                    session_id=learning.id,
                    checkin_date=today,
                    timezone_name="Asia/Shanghai",
                    is_valid=1,
                )
                self.session.add(record)
                await self.session.flush()
                await self.session.refresh(record)
                await social.record_activity(
                    self.session,
                    claims.user_id,
                    route.id,
                    "checkin",
                    f"checkin:{record.id}",
                    today,
                    checkin_id=record.id,
                )
            return self.record_data(record)

    async def dismiss_update(self, enrollment_id, claims, data):
        """仅抑制所见新版的提示；新版标记和订阅均保留，后续版本重新提示。"""
        async with self.session.begin():
            relation, route, learning, release = await self.context(
                enrollment_id, claims, write=True
            )
            current = (
                await self.session.get(RoadmapRelease, route.current_release_id)
                if route.current_release_id
                else None
            )
            author = await roadmaps.get_author(self.session, route.creator_id)
            if (
                not is_public_route(route, current, author)
                or current.id != data.release_id
                or current.version_no <= release.version_no
            ):
                raise AppError(409, "RELEASE_CHANGED", "新版已变化，请刷新后重试")
            relation.dismissed_release_id = current.id if data.dismissed else None
            relation.updated_at = now()
            await self.session.flush()
            return await self.summary(relation, route, learning, release, lock=True)

    async def records(self, enrollment_id, claims, page, page_size):
        async with self.session.begin():
            relation, _, _, _ = await self.context(enrollment_id, claims)
            today = self.today()
            total, rows = await crud.record_rows(self.session, relation.id, page, page_size)
            record = await crud.record_for_day(self.session, relation.id, today)
            return {
                "items": [self.record_data(r) for r in rows],
                "total": total,
                "today": today.isoformat(),
                "checkedInToday": record is not None,
                "page": page,
                "pageSize": page_size,
            }

    async def overview(self, current, month=None):
        """本人日历与累计/连续天数只聚合有效日期，不暴露其他用户记录。"""
        async with self.session.begin():
            await authenticated_account(self.session, current.claims)
            today = self.today()
            month = month or today.strftime("%Y-%m")
            dates = await crud.checkin_dates(self.session, current.user.id)
            days, streak, longest = day_statistics(dates, today)
            learning, completed = await crud.overview_counts(self.session, current.user.id)
            return {
                "learningRoadmapCount": learning,
                "completedNodeCount": completed,
                "checkinDayCount": days,
                "currentStreak": streak,
                "longestStreak": longest,
                "today": today.isoformat(),
                "month": month,
                "calendarDates": [
                    d.isoformat() for d in dates if d.strftime("%Y-%m") == month and d <= today
                ],
            }
