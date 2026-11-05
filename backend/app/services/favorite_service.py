"""社区发现及收藏事务；公开摘要、个人关系和学习授权相互独立。"""

from uuid import uuid4
from zoneinfo import ZoneInfo

from app.core.exceptions import AppError
from app.core.security import utc_now
from app.database.crud import favorite as crud
from app.database.crud import roadmap as roadmaps
from app.database.crud import user as social
from app.database.models import RoadmapFavorite, RoadmapRelease
from app.domain.roadmap_policy import is_public_route
from app.schemas.common import serialize_utc
from app.services.auth_service import authenticated_account


class FavoriteService:
    """公开卡片使用冻结版，收藏写入按路线→账号顺序加锁复核。"""

    def __init__(self, session):
        self.session = session

    async def cards(self, rows, viewer):
        """一次批量统计当前页，不逐条查询关联计数。"""
        learners, favorites, mine = await crud.engagement_counts(
            self.session, [r.id for r, _, _ in rows], viewer
        )
        stages, nodes = await crud.release_counts(self.session, [v.id for _, v, _ in rows])
        return [
            {
                "id": str(route.id),
                "title": release.title,
                "description": release.summary,
                "difficulty": release.difficulty,
                "coverUrl": None,
                "roadmapType": route.roadmap_type,
                "releaseId": str(release.id),
                "versionNo": release.version_no,
                "publishedAt": serialize_utc(release.published_at),
                "stageCount": stages.get(release.id, 0),
                "nodeCount": nodes.get(release.id, 0),
                "learnerCount": learners.get(route.id, 0),
                "favoriteCount": favorites.get(route.id, 0),
                "isFavorited": route.id in mine,
                "isOwner": route.creator_id == viewer,
                "author": {
                    "id": str(author.id),
                    "username": author.username,
                    "nickname": author.nickname,
                    "avatarUrl": author.avatar_url,
                    "bio": author.bio,
                },
            }
            for route, release, author in rows
        ]

    async def community(
        self, current, query, difficulty, page, page_size, sort_by="publishedAt", order="desc"
    ):
        """匿名也可发现当前公开路线；查询不产生任何个人关系。"""
        async with self.session.begin():
            if current:
                await authenticated_account(self.session, current.claims)
            total, rows = await crud.public_routes(
                self.session, query.strip(), difficulty, page, page_size, sort_by, order
            )
            return {
                "items": await self.cards(rows, current.user.id if current else None),
                "total": total,
                "page": page,
                "pageSize": page_size,
            }

    async def listing(self, current, page, page_size):
        """不可访问的收藏只返回最小摘要，重发后自动读取当前新版。"""
        async with self.session.begin():
            await authenticated_account(self.session, current.claims)
            total, rows = await crud.favorite_rows(self.session, current.user.id, page, page_size)
            public = [(r, v, u) for _, r, v, u in rows if is_public_route(r, v, u)]
            cards = {item["id"]: item for item in await self.cards(public, current.user.id)}
            items = []
            for favorite, route, release, _ in rows:
                card = cards.get(str(route.id))
                restricted = route.moderation_status == "disabled" or (
                    release is not None and release.content_access != "normal"
                )
                title = "内容已下架" if restricted else "路线暂不可访问"
                items.append(
                    {
                        "roadmapId": str(route.id),
                        "title": card["title"] if card else title,
                        "status": "disabled" if restricted else route.distribution_status,
                        "accessible": card is not None,
                        "favoritedAt": serialize_utc(favorite.created_at),
                        "roadmap": card,
                    }
                )
            return {"items": items, "total": total, "page": page, "pageSize": page_size}

    async def detail(self, route_id, current):
        """游客和作者均读取当前公开快照；工作稿预览使用独立显式授权。"""
        async with self.session.begin():
            if current:
                await authenticated_account(self.session, current.claims)
            route = await roadmaps.get_route(self.session, route_id)
            release = (
                await self.session.get(RoadmapRelease, route.current_release_id)
                if route and route.current_release_id
                else None
            )
            author = await roadmaps.get_author(self.session, route.creator_id) if route else None
            if not route or not is_public_route(route, release, author):
                raise AppError(404, "ROADMAP_NOT_FOUND", "路线不存在或不可访问")
            viewer = current.user.id if current else None
            card = (await self.cards([(route, release, author)], viewer))[0]
            stages, nodes = await crud.public_structure(self.session, release.id)
            edges = await roadmaps.release_edges(self.session, release.id)
            from app.database.crud import enrollment as learning_crud

            relation = (
                await learning_crud.find_enrollment(self.session, viewer, route.id)
                if viewer
                else None
            )
            return {
                **card,
                "status": "published",
                "displayStatus": "已发布",
                "updatedAt": serialize_utc(release.published_at),
                "effortNote": release.effort_note,
                "licenseCode": release.license_code,
                "licenseUrl": release.license_url,
                "updateSummary": release.update_summary,
                "canMaintain": route.creator_id == viewer,
                "canFavorite": route.creator_id != viewer,
                "canStartLearning": route.creator_id != viewer,
                "learning": {"id": str(relation.id), "status": relation.status}
                if relation
                else None,
                "canDelete": False,
                "authorArchivedAt": None,
                "canReadContent": False,
                "contentSource": None,
                "stages": [
                    {
                        "id": str(s.id),
                        "title": s.title,
                        "canvasX": float(s.canvas_x),
                        "canvasY": float(s.canvas_y),
                        "nodes": [
                            {
                                "id": str(n.id),
                                "title": n.title,
                                "canvasX": float(n.canvas_x),
                                "canvasY": float(n.canvas_y),
                            }
                            for n in nodes
                            if n.stage_id == s.id
                        ],
                    }
                    for s in stages
                ],
                "connections": [
                    {"source": str(e.source_stage_id), "target": str(e.target_stage_id)}
                    for e in edges
                ],
            }

    async def change(self, route_id, claims, enabled):
        """幂等收藏或取消；作者自收藏403，受限来源仍允许本人取消。"""
        async with self.session.begin():
            route = await roadmaps.get_route(self.session, route_id, lock=True)
            await authenticated_account(self.session, claims, lock=True)
            if route is None:
                raise AppError(404, "ROADMAP_NOT_FOUND", "路线不存在或不可访问")
            if enabled and route.creator_id == claims.user_id:
                raise AppError(403, "SELF_FAVORITE_FORBIDDEN", "不能收藏本人创作的路线")
            release = (
                await self.session.get(RoadmapRelease, route.current_release_id)
                if route.current_release_id
                else None
            )
            author = await roadmaps.get_author(self.session, route.creator_id)
            public = is_public_route(route, release, author)
            if enabled and not public:
                raise AppError(404, "ROADMAP_NOT_FOUND", "路线不存在或不可访问")
            favorite = await crud.get_favorite(self.session, route_id, claims.user_id)
            if (
                not enabled
                and favorite is None
                and route.creator_id != claims.user_id
                and not public
            ):
                raise AppError(404, "ROADMAP_NOT_FOUND", "路线不存在或不可访问")
            if enabled and favorite is None:
                self.session.add(RoadmapFavorite(user_id=claims.user_id, roadmap_id=route_id))
                await social.record_activity(
                    self.session,
                    claims.user_id,
                    route_id,
                    "favorite",
                    f"favorite:{uuid4()}",
                    utc_now()
                    .replace(tzinfo=ZoneInfo("UTC"))
                    .astimezone(ZoneInfo("Asia/Shanghai"))
                    .date(),
                )
            elif not enabled and favorite is not None:
                await social.deactivate_activity(self.session, claims.user_id, route_id, "favorite")
                await self.session.delete(favorite)
            await self.session.flush()
            return {
                "roadmapId": str(route_id),
                "isFavorited": enabled,
                "favoriteCount": await crud.favorite_count(self.session, route_id),
            }

    async def subscription(self, route_id, claims, data=None):
        """独立读写路线更新订阅；归档或下架仍允许已有订阅退订。"""
        from app.database.models import RoadmapSubscription
        from app.services.user_service import UserService

        async with self.session.begin():
            route = await roadmaps.get_route(self.session, route_id, lock=data is not None)
            UserService.require_community(
                await authenticated_account(self.session, claims, lock=data is not None)
            )
            if not route:
                raise AppError(404, "ROADMAP_NOT_FOUND", "路线不存在或不可访问")
            row = await social.roadmap_subscription(
                self.session, claims.user_id, route_id, lock=data is not None
            )
            release = (
                await self.session.get(RoadmapRelease, route.current_release_id)
                if route.current_release_id
                else None
            )
            author = await roadmaps.get_author(self.session, route.creator_id)
            public = is_public_route(route, release, author)
            if not public and (not row or (data is not None and data.subscribed)):
                raise AppError(404, "ROADMAP_NOT_FOUND", "路线不存在或不可访问")
            if data is not None:
                if route.creator_id == claims.user_id and data.subscribed:
                    raise AppError(403, "SELF_SUBSCRIPTION_FORBIDDEN", "不能订阅本人路线更新")
                if row is None:
                    row = RoadmapSubscription(user_id=claims.user_id, roadmap_id=route_id)
                    self.session.add(row)
                row.is_subscribed = int(data.subscribed)
                row.updated_at = utc_now()
                await self.session.flush()
            return {"subscribed": bool(row and row.is_subscribed)}
