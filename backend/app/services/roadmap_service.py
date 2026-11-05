"""R03工作稿、稳定任务身份与不可变发布事务。"""

import hashlib
import json
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import AppError
from app.core.security import utc_now
from app.database.crud import favorite as engagement
from app.database.crud import roadmap as crud
from app.database.models import (
    ActivityEvent,
    LearningNode,
    NodeResource,
    NotificationOutbox,
    ReleaseNode,
    ReleaseResource,
    ReleaseStage,
    ReleaseStageEdge,
    RoadmapRelease,
    RoadmapStage,
    RoadmapStageEdge,
    SkillRoadmap,
)
from app.domain.roadmap_policy import publication_issues, require_editable
from app.schemas.common import serialize_utc
from app.schemas.roadmap import RoadmapSave, content_key
from app.services.auth_service import authenticated_account


def not_found():
    return AppError(404, "ROADMAP_NOT_FOUND", "路线不存在或不可访问")


def content_hash(document):
    """忽略数据库/临时ID与乐观锁，冻结稳定身份、语义及完整内容。"""
    data = document.model_dump(mode="json")
    data.pop("expectedVersion", None)
    stage_keys = {s["id"]: s["stableKey"] for s in data["stages"]}
    for stage in data["stages"]:
        stage.pop("id")
        for node in stage["nodes"]:
            node.pop("id")
            for resource in node["resources"]:
                resource.pop("id")
    data["connections"] = sorted(
        [
            {"source": stage_keys[e["source"]], "target": stage_keys[e["target"]]}
            for e in data["connections"]
        ],
        key=lambda e: (e["source"], e["target"]),
    )
    return hashlib.sha256(
        json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class RoadmapService:
    """服务拥有完整事务，路线锁后复核本人账号及持久登录会话。"""

    def __init__(self, session, request_id="internal"):
        self.session = session
        self.request_id = request_id

    async def administrator(self, claims, *, lock=False):
        """每个后台事务复核持久身份与当前角色，写入前再次锁定账号。"""
        user = await authenticated_account(self.session, claims, lock=lock)
        if user.role != "admin":
            raise AppError(403, "ADMIN_REQUIRED", "需要管理员权限")
        return user

    async def moderation_summary(self, route, release, author, counts=None):
        """审核摘要只读发布数据，工作稿标题及正文不进入后台。"""
        if counts is None:
            learners, favorites, _ = await engagement.engagement_counts(
                self.session, [route.id], None
            )
            stages, nodes = await engagement.release_counts(self.session, [release.id])
        else:
            learners, favorites, stages, nodes = counts
        status = self.status(route)
        return {
            "id": str(route.id),
            "title": release.title,
            "description": release.summary,
            "difficulty": release.difficulty,
            "status": status,
            "displayStatus": {
                "published": "已发布",
                "archived": "作者归档",
                "draft": "草稿",
                "disabled": "已下架",
            }[status],
            "editVersion": route.edit_version,
            "releaseId": str(release.id),
            "versionNo": release.version_no,
            "stageCount": stages.get(release.id, 0),
            "nodeCount": nodes.get(release.id, 0),
            "publishedAt": serialize_utc(release.published_at),
            "updatedAt": serialize_utc(route.updated_at),
            "learnerCount": learners.get(route.id, 0),
            "favoriteCount": favorites.get(route.id, 0),
            "author": {
                "id": str(author.id),
                "username": author.username,
                "nickname": author.nickname,
            },
            "roadmapType": route.roadmap_type,
            "canMaintain": False,
            "isOwner": False,
            "canFavorite": False,
            "canStartLearning": False,
            "canDelete": False,
            "coverUrl": None,
            "authorArchivedAt": None,
            "disabledReason": None,
        }

    async def admin_listing(
        self, claims, keyword, difficulty, status, sort_by, order, page, page_size
    ):
        """分页审核发布路线；不开放任意读取他人草稿的能力。"""
        async with self.session.begin():
            await self.administrator(claims)
            total, rows = await crud.moderation_routes(
                self.session, keyword.strip(), difficulty, status, sort_by, order, page, page_size
            )
            learners, favorites, _ = await engagement.engagement_counts(
                self.session, [r.id for r, _, _ in rows], None
            )
            stages, nodes = await engagement.release_counts(
                self.session, [v.id for _, v, _ in rows]
            )
            counts = (learners, favorites, stages, nodes)
            return {
                "items": [await self.moderation_summary(*row, counts=counts) for row in rows],
                "total": total,
                "page": page,
                "pageSize": page_size,
            }

    async def official_listing(self, claims, archived, page, page_size, keyword="", status=None):
        """官方工作稿属于平台，多管理员使用同一版本锁维护。"""
        async with self.session.begin():
            await self.administrator(claims)
            total, rows = await crud.official_routes(
                self.session, archived, page, page_size, keyword.strip(), status
            )
            items = []
            for route in rows:
                item = await self.summary(route, claims.user_id)
                item.update(canMaintain=True, canManageOfficial=True)
                items.append(item)
            return {"items": items, "total": total, "page": page, "pageSize": page_size}

    async def admin_detail(self, route_id, claims, release_id=None):
        """管理员可审核下架或历史发布版；从不回退到用户的未发布工作稿。"""
        async with self.session.begin():
            await self.administrator(claims)
            route = await crud.get_route(self.session, route_id)
            if not route or not route.current_release_id:
                raise not_found()
            releases = await crud.route_releases(self.session, route.id)
            release = next(
                (r for r in releases if r.id == (release_id or route.current_release_id)), None
            )
            if release is None:
                raise not_found()
            author = await crud.get_author(self.session, route.creator_id)
            result = await self.moderation_summary(route, release, author)
            _, stages, nodes, resources = await crud.release_rows(self.session, release.id)
            edges = await crud.release_edges(self.session, release.id)
            result.update(
                stages=[
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
                                "tips": n.tips,
                                "estimatedMinutes": n.estimated_minutes,
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
                ],
                connections=[
                    {"source": str(e.source_stage_id), "target": str(e.target_stage_id)}
                    for e in edges
                ],
                releases=[
                    {
                        "id": str(r.id),
                        "versionNo": r.version_no,
                        "title": r.title,
                        "publishedAt": serialize_utc(r.published_at),
                    }
                    for r in releases
                ],
                updateSummary=release.update_summary,
                contentSource="published",
                canReadContent=True,
                isFavorited=False,
                learning=None,
                moderationHistory=[
                    {
                        "id": str(h.id),
                        "action": h.action,
                        "reason": h.reason,
                        "actorId": str(h.actor_id),
                        "createdAt": serialize_utc(h.created_at),
                    }
                    for h in await crud.moderation_history(self.session, route.id)
                ],
            )
            return result

    async def moderate(self, route_id, claims, data, action):
        """路线行锁串行化下架/恢复，仅改变治理状态，保留快照限制与全部学习事实。"""
        async with self.session.begin():
            route = await crud.get_route(self.session, route_id, lock=True)
            await self.administrator(claims, lock=True)
            if not route or not route.current_release_id:
                raise not_found()
            self.version(route, data.expected_version)
            target = "disabled" if action == "disable" else "normal"
            if route.moderation_status == target:
                return {
                    "id": str(route.id),
                    "status": self.status(route),
                    "editVersion": route.edit_version,
                }
            before = {"moderationStatus": route.moderation_status}
            route.moderation_status = target
            route.edit_version += 1
            route.updated_at = utc_now()
            crud.add_moderation(
                self.session,
                claims.user_id,
                route.id,
                action,
                data.reason,
                before,
                {"moderationStatus": target},
                request_id=self.request_id,
            )
            await self.session.flush()
            return {
                "id": str(route.id),
                "status": self.status(route),
                "editVersion": route.edit_version,
            }

    async def owned(self, route_id, claims):
        """社区作者仅维护本人内容；管理员仅共同维护官方路线。"""
        route = await crud.get_route(self.session, route_id, lock=True)
        user = await authenticated_account(self.session, claims, lock=True)
        allowed = route and (
            route.roadmap_type == "official"
            if user.role == "admin"
            else route.roadmap_type == "user" and route.creator_id == claims.user_id
        )
        if not allowed:
            raise not_found()
        return route

    @staticmethod
    def version(route, expected):
        if route.edit_version != expected:
            raise AppError(
                409,
                "EDIT_VERSION_CONFLICT",
                "路线已发生变化，请重新加载",
                {"currentVersion": route.edit_version},
            )

    @staticmethod
    def status(route):
        return "disabled" if route.moderation_status == "disabled" else route.distribution_status

    async def create(self, claims, data):
        """创建不完整草稿，不发布、不建立学习关系。"""
        async with self.session.begin():
            user = await authenticated_account(self.session, claims, lock=True)
            if (data.roadmap_type == "official") != (user.role == "admin"):
                raise AppError(
                    403,
                    "ROADMAP_TYPE_FORBIDDEN",
                    "管理员只能创建官方路线，普通用户只能创建社区路线",
                )
            route = SkillRoadmap(
                creator_id=claims.user_id, title=data.title, roadmap_type=data.roadmap_type
            )
            self.session.add(route)
            await self.session.flush()
            await self.session.refresh(route)
            return {"id": str(route.id), "editVersion": route.edit_version}

    async def summary(self, route, viewer):
        """作者仓库读工作稿标题，并显示独立的当前公开版与待发布状态。"""
        author = await crud.get_author(self.session, route.creator_id)
        release = (
            await self.session.get(RoadmapRelease, route.current_release_id)
            if route.current_release_id
            else None
        )
        document = await self.draft_document(route)
        status = self.status(route)
        return {
            "id": str(route.id),
            "title": route.title,
            "description": route.summary,
            "difficulty": route.difficulty,
            "coverUrl": None,
            "roadmapType": route.roadmap_type,
            "effortNote": route.effort_note,
            "licenseCode": route.license_code,
            "licenseUrl": route.license_url,
            "status": status,
            "displayStatus": {
                "draft": "草稿",
                "published": "已发布",
                "archived": "已归档",
                "disabled": "内容已下架",
            }[status],
            "editVersion": route.edit_version,
            "stageCount": len(document.stages),
            "nodeCount": sum(len(s.nodes) for s in document.stages),
            "updatedAt": serialize_utc(route.updated_at),
            "publishedAt": serialize_utc(release.published_at) if release else None,
            "releaseId": str(release.id) if release else None,
            "versionNo": release.version_no if release else None,
            "publishedTitle": release.title if release else None,
            "updateSummary": release.update_summary if release else None,
            "hasUnpublishedChanges": release is None
            or content_hash(document) != release.content_hash,
            "authorArchivedAt": serialize_utc(route.author_archived_at)
            if route.author_archived_at
            else None,
            "isOwner": viewer == route.creator_id,
            "canMaintain": viewer == route.creator_id,
            "canDelete": release is None and route.distribution_status == "draft",
            "canFavorite": False,
            "canStartLearning": False,
            "disabledReason": None,
            "author": {
                "id": str(author.id),
                "username": author.username,
                "nickname": author.nickname,
            },
        }

    async def listing(self, current, archived, state, query, page, page_size):
        async with self.session.begin():
            await authenticated_account(self.session, current.claims)
            total, rows = await crud.author_routes(
                self.session, current.user.id, archived, state, query, page, page_size
            )
            return {
                "items": [await self.summary(r, current.user.id) for r in rows],
                "total": total,
                "page": page,
                "pageSize": page_size,
            }

    async def draft_document(self, route):
        """返回有序工作稿；公开端从不调用本方法。"""
        stages, nodes, resources = await crud.draft_rows(self.session, route.id)
        edges = await crud.edges(self.session, route.id)
        return RoadmapSave(
            expected_version=route.edit_version,
            title=route.title,
            description=route.summary,
            difficulty=route.difficulty,
            effort_note=route.effort_note,
            license_code=route.license_code,
            license_url=route.license_url,
            stages=[
                {
                    "id": str(s.id),
                    "stableKey": s.stable_key,
                    "title": s.title,
                    "description": s.description,
                    "canvasX": float(s.canvas_x),
                    "canvasY": float(s.canvas_y),
                    "nodes": [
                        {
                            "id": str(n.id),
                            "stableKey": n.stable_key,
                            "revisionNo": n.revision_no,
                            "title": n.title,
                            "content": n.content or "",
                            "tips": n.tips,
                            "estimatedMinutes": n.estimated_minutes,
                            "isOptional": bool(n.is_optional),
                            "countsTowardProgress": bool(n.counts_toward_progress),
                            "changePolicy": n.change_policy,
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
            ],
            connections=[
                {"source": str(e.source_stage_id), "target": str(e.target_stage_id)} for e in edges
            ],
        )

    async def draft_response(self, route, id_map=None):
        return {
            "id": str(route.id),
            "status": self.status(route),
            "authorArchivedAt": serialize_utc(route.author_archived_at)
            if route.author_archived_at
            else None,
            "document": (await self.draft_document(route)).model_dump(mode="json"),
            "idMap": id_map or {},
        }

    async def draft(self, route_id, claims):
        async with self.session.begin():
            route = await self.owned(route_id, claims)
            if route.moderation_status == "disabled":
                raise AppError(403, "ROADMAP_DISABLED", "内容已下架")
            return await self.draft_response(route)

    async def detail(self, route_id, current=None, enrollment_id=None, preview=None):
        """默认只读公开摘要；工作稿正文需显式预览并再次校验作者身份。"""
        if preview != "draft":
            from app.services.favorite_service import FavoriteService

            return await FavoriteService(self.session).detail(route_id, current)
        if current is None:
            raise AppError(401, "UNAUTHORIZED", "请先登录")
        async with self.session.begin():
            route = await self.owned(route_id, current.claims)
            if route.moderation_status == "disabled":
                raise AppError(403, "ROADMAP_DISABLED", "内容已下架")
            result = await self.summary(route, current.user.id)
            if current.user.role == "admin" and route.roadmap_type == "official":
                result.update(canMaintain=True, canManageOfficial=True)
            document = await self.draft_document(route)
            learners, favorites, _ = await engagement.engagement_counts(
                self.session, [route.id], current.user.id
            )
            result.update(
                stages=[s.model_dump(mode="json") for s in document.stages],
                connections=[e.model_dump(mode="json") for e in document.connections],
                canReadContent=True,
                contentSource="draft",
                learning=None,
                learnerCount=learners.get(route.id, 0),
                favoriteCount=favorites.get(route.id, 0),
                isFavorited=False,
            )
            return result

    async def save(self, route_id, claims, data):
        """整图保存：复用原身份，软删除阶段/节点，边与资源单独重排。"""
        async with self.session.begin():
            route = await self.owned(route_id, claims)
            require_editable(self.status(route), route.author_archived_at is not None)
            self.version(route, data.expected_version)
            before = await self.draft_document(route)
            # 相同完整工作稿不递增版本或语义修订号。
            if before.model_dump(mode="json") == data.model_dump(mode="json"):
                return await self.draft_response(route)
            stages, nodes, resources = await crud.draft_rows(
                self.session, route_id, include_deleted=True
            )
            stage_by_id = {s.id: s for s in stages}
            node_by_id = {n.id: n for n in nodes}
            resource_by_id = {r.id: r for r in resources}
            id_map, kept_stages, kept_nodes = {}, set(), set()
            stage_map = {}

            def existing(value, mapping):
                key = content_key(value)
                if key is not None and key not in mapping:
                    raise AppError(409, "CONTENT_ID_CONFLICT", "内容ID不属于此路线")
                return mapping.get(key)

            # 在任何删除前核验全部ID和服务端生成的稳定身份。
            for s in data.stages:
                original = existing(s.id, stage_by_id)
                if s.stable_key and (original is None or str(s.stable_key) != original.stable_key):
                    raise AppError(409, "STABLE_ID_CONFLICT", "阶段稳定身份不可修改")
                for n in s.nodes:
                    original_node = existing(n.id, node_by_id)
                    if (
                        n.stable_key
                        and (original_node is None or str(n.stable_key) != original_node.stable_key)
                        or n.revision_no is not None
                        and (original_node is None or n.revision_no != original_node.revision_no)
                    ):
                        raise AppError(
                            409, "STABLE_ID_CONFLICT", "节点稳定身份和修订号由服务端维护"
                        )
                    for r in n.resources:
                        original_resource = existing(r.id, resource_by_id)
                        if original_resource and (
                            original_node is None or original_resource.node_id != original_node.id
                        ):
                            raise AppError(409, "CONTENT_ID_CONFLICT", "资源不属于此节点")
            # 资源不承载稳定身份，可删除后重建以避免位置唯一键交换冲突。
            node_ids = select(LearningNode.id).where(LearningNode.roadmap_id == route_id)
            await self.session.execute(
                delete(NodeResource).where(NodeResource.node_id.in_(node_ids))
            )
            await self.session.execute(
                delete(RoadmapStageEdge).where(RoadmapStageEdge.roadmap_id == route_id)
            )
            now = utc_now()
            for position, s in enumerate(data.stages, 1):
                stage = existing(s.id, stage_by_id)
                if stage is None:
                    stage = RoadmapStage(roadmap_id=route_id, stable_key=str(uuid4()))
                    self.session.add(stage)
                stage.title, stage.description = s.title, s.description
                stage.position, stage.canvas_x, stage.canvas_y = position, s.canvas_x, s.canvas_y
                stage.is_deleted, stage.updated_at = 0, now
                await self.session.flush()
                if content_key(s.id) is None:
                    id_map[s.id] = str(stage.id)
                stage_map[s.id] = stage.id
                kept_stages.add(stage.id)
                for index, n in enumerate(s.nodes, 1):
                    node = existing(n.id, node_by_id)
                    if node is None:
                        node = LearningNode(
                            roadmap_id=route_id,
                            stage_id=stage.id,
                            stable_key=str(uuid4()),
                            revision_no=1,
                        )
                        self.session.add(node)
                    elif n.change_policy == "reconfirm" and (
                        node.change_policy != "reconfirm"
                        or node.title != n.title
                        or node.content != n.content
                        or node.tips != n.tips
                        or [
                            (r.title, r.url, r.resource_type, r.language_code, r.access_type)
                            for r in resources
                            if r.node_id == node.id
                        ]
                        != [
                            (
                                r.title,
                                r.resource_url,
                                r.resource_type.value,
                                r.language_code,
                                r.access_type,
                            )
                            for r in n.resources
                        ]
                    ):
                        node.revision_no += 1
                    node.stage_id, node.title, node.content, node.tips = (
                        stage.id,
                        n.title,
                        n.content,
                        n.tips,
                    )
                    node.position, node.canvas_x, node.canvas_y = index, n.canvas_x, n.canvas_y
                    node.estimated_minutes = n.estimated_minutes
                    node.is_optional, node.counts_toward_progress = (
                        int(n.is_optional),
                        int(n.counts_toward_progress),
                    )
                    node.change_policy, node.is_deleted, node.updated_at = n.change_policy, 0, now
                    await self.session.flush()
                    if content_key(n.id) is None:
                        id_map[n.id] = str(node.id)
                    kept_nodes.add(node.id)
                    for resource_position, r in enumerate(n.resources, 1):
                        resource = NodeResource(
                            node_id=node.id,
                            title=r.title,
                            url=r.resource_url,
                            resource_type=r.resource_type.value,
                            position=resource_position,
                            access_type=r.access_type,
                            language_code=r.language_code,
                        )
                        self.session.add(resource)
                        await self.session.flush()
                        if content_key(r.id) is None:
                            id_map[r.id] = str(resource.id)
            for stage in stages:
                if stage.id not in kept_stages:
                    stage.is_deleted, stage.updated_at = 1, now
            for node in nodes:
                if node.id not in kept_nodes:
                    node.is_deleted, node.updated_at = 1, now
            for edge in data.connections:
                self.session.add(
                    RoadmapStageEdge(
                        roadmap_id=route_id,
                        source_stage_id=stage_map[edge.source],
                        target_stage_id=stage_map[edge.target],
                    )
                )
            route.title, route.summary, route.difficulty = (
                data.title,
                data.description or "",
                data.difficulty.value,
            )
            route.effort_note = (data.effort_note or "").strip() or None
            route.license_code, route.license_url = data.license_code, data.license_url or None
            route.edit_version += 1
            route.updated_at = now
            await self.session.flush()
            return await self.draft_response(route, id_map)

    async def validate(self, route_id, claims, expected):
        async with self.session.begin():
            route = await self.owned(route_id, claims)
            require_editable(self.status(route), route.author_archived_at is not None)
            self.version(route, expected)
            data = await self.draft_document(route)
            return {
                "issues": publication_issues(data),
                "nextVersionNo": (await crud.release_count(self.session, route_id)) + 1,
            }

    @staticmethod
    def publication_result(route, release):
        return {
            "id": str(route.id),
            "releaseId": str(release.id),
            "versionNo": release.version_no,
            "editVersion": route.edit_version,
        }

    async def publish(self, route_id, claims, expected, update_summary):
        """头锁串行发布；快照、指针、活动和outbox同事务提交或回滚。"""
        async with self.session.begin():
            route = await self.owned(route_id, claims)
            require_editable(self.status(route), route.author_archived_at is not None)
            self.version(route, expected)
            data = await self.draft_document(route)
            digest = content_hash(data)
            prior = await self.session.scalar(
                select(RoadmapRelease).where(
                    RoadmapRelease.roadmap_id == route_id,
                    RoadmapRelease.source_edit_version == expected,
                )
            )
            if prior:
                if prior.update_summary != update_summary:
                    raise AppError(409, "PUBLISH_REQUEST_CONFLICT", "此工作稿已按另一更新说明发布")
                return self.publication_result(route, prior)
            current = (
                await self.session.get(RoadmapRelease, route.current_release_id)
                if route.current_release_id
                else None
            )
            if current and current.content_hash == digest:
                return self.publication_result(route, current)
            issues = publication_issues(data)
            if issues:
                raise AppError(422, "PUBLICATION_INVALID", "请完成发布检查", {"issues": issues})
            now = utc_now()
            release = RoadmapRelease(
                roadmap_id=route_id,
                version_no=(await crud.release_count(self.session, route_id)) + 1,
                source_edit_version=expected,
                title=route.title,
                summary=route.summary,
                difficulty=route.difficulty,
                effort_note=route.effort_note,
                license_code=route.license_code,
                license_url=route.license_url,
                update_summary=update_summary,
                content_hash=digest,
                published_by=claims.user_id,
                published_at=now,
                content_access="normal",
            )
            self.session.add(release)
            await self.session.flush()
            stage_map = {}
            for index, stage in enumerate(data.stages, 1):
                frozen_stage = ReleaseStage(
                    release_id=release.id,
                    stable_key=str(stage.stable_key),
                    position=index,
                    title=stage.title,
                    description=stage.description,
                    canvas_x=stage.canvas_x,
                    canvas_y=stage.canvas_y,
                )
                self.session.add(frozen_stage)
                await self.session.flush()
                stage_map[stage.id] = frozen_stage.id
                for j, node in enumerate(stage.nodes, 1):
                    frozen_node = ReleaseNode(
                        release_id=release.id,
                        stage_id=frozen_stage.id,
                        position=j,
                        stable_key=str(node.stable_key),
                        revision_no=node.revision_no,
                        title=node.title,
                        content=node.content,
                        tips=node.tips,
                        estimated_minutes=node.estimated_minutes,
                        is_optional=int(node.is_optional),
                        counts_toward_progress=int(node.counts_toward_progress),
                        change_policy=node.change_policy,
                        canvas_x=node.canvas_x,
                        canvas_y=node.canvas_y,
                    )
                    self.session.add(frozen_node)
                    await self.session.flush()
                    for k, resource in enumerate(node.resources, 1):
                        self.session.add(
                            ReleaseResource(
                                release_id=release.id,
                                node_id=frozen_node.id,
                                position=k,
                                title=resource.title,
                                resource_type=resource.resource_type.value,
                                url=resource.resource_url,
                                access_type=resource.access_type,
                                language_code=resource.language_code,
                            )
                        )
            for edge in data.connections:
                self.session.add(
                    ReleaseStageEdge(
                        release_id=release.id,
                        source_stage_id=stage_map[edge.source],
                        target_stage_id=stage_map[edge.target],
                    )
                )
            event_key = f"release:{release.id}:published"
            self.session.add(
                ActivityEvent(
                    actor_id=claims.user_id,
                    activity_type="publish",
                    roadmap_id=route_id,
                    release_id=release.id,
                    event_key=event_key,
                    visibility="public",
                    is_active=1,
                    occurred_on=now.replace(tzinfo=ZoneInfo("UTC"))
                    .astimezone(ZoneInfo("Asia/Shanghai"))
                    .date(),
                    created_at=now,
                )
            )
            self.session.add(
                NotificationOutbox(
                    event_key=event_key,
                    event_type="release_published",
                    payload={
                        "roadmapId": str(route_id),
                        "releaseId": str(release.id),
                        "actorId": str(claims.user_id),
                    },
                    available_at=now,
                )
            )
            route.current_release_id, route.distribution_status = release.id, "published"
            route.published_at, route.updated_at = now, now
            # 发布不改变工作稿修订号，重试仍指向同一source_edit_version。
            await self.session.flush()
            return self.publication_result(route, release)

    async def transition(self, route_id, claims, expected, action):
        """发布后只允许归档与恢复；恢复重新展示原公开版，不创建新快照。"""
        async with self.session.begin():
            route = await self.owned(route_id, claims)
            self.version(route, expected)
            if action == "withdraw":
                raise AppError(409, "ARCHIVE_REQUIRED", "请使用归档管理已发布路线")
            if not route.current_release_id:
                raise AppError(409, "DRAFT_DELETE_REQUIRED", "未发布草稿请使用删除")
            if action == "archive" and route.author_archived_at is None:
                route.author_archived_at = utc_now()
                route.distribution_status = "archived"
                route.updated_at = utc_now()
            elif action == "restore" and route.author_archived_at is not None:
                route.author_archived_at = None
                route.distribution_status = "published"
                route.updated_at = utc_now()
            await self.session.flush()
            return {"id": str(route.id), "editVersion": route.edit_version}

    async def delete_draft(self, route_id, claims, expected):
        """无发布及对外引用才可按外键顺序物理清理，任何失败均整体回滚。"""
        try:
            async with self.session.begin():
                route = await self.owned(route_id, claims)
                self.version(route, expected)
                if (
                    route.current_release_id
                    or route.distribution_status != "draft"
                    or route.moderation_status != "normal"
                    or await crud.release_count(self.session, route_id)
                ):
                    raise AppError(409, "HISTORY_MUST_BE_PRESERVED", "曾发布路线只能归档")
                await crud.delete_draft_graph(self.session, route_id)
        except IntegrityError as cause:
            raise AppError(409, "HISTORY_MUST_BE_PRESERVED", "路线存在关联历史，未删除") from cause
