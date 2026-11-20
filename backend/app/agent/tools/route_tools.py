"""只读路线工具；复用业务 service，不把身份和数据库参数暴露给模型。"""

from typing import Annotated

from langchain_core.tools import tool
from pydantic import Field, StringConstraints

from app.config.enums import Difficulty
from app.schemas.common import JsonId
from app.services.favorite_service import FavoriteService
from app.services.roadmap_service import RoadmapService

Keyword = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]


def create_tools(current, sessions):
    """绑定本次登录身份和 session 工厂；仅在真正查询时打开独立 session。"""

    @tool
    async def search_routes(
        keyword: Keyword,
        difficulty: Difficulty | None = None,
        page: Annotated[int, Field(ge=1, le=1000000)] = 1,
    ) -> dict:
        """搜索站内公开路线，每页 6 条；keyword 为空可浏览，可指定难度和页码。"""
        async with sessions() as session:
            result = await FavoriteService(session).community(current, keyword, difficulty, page, 6)
        fields = (
            "id",
            "title",
            "description",
            "difficulty",
            "stageCount",
            "nodeCount",
            "learnerCount",
            "favoriteCount",
        )
        return {
            "items": [
                {**{key: item[key] for key in fields}, "url": f"/roadmaps/{item['id']}"}
                for item in result["items"]
            ],
            "total": result["total"],
            "page": result["page"],
            "pageSize": result["pageSize"],
        }

    @tool
    async def get_route_detail(route_id: JsonId) -> dict:
        """读取指定站内路线的公开介绍和阶段、节点标题，不读取工作稿或学习正文。"""
        async with sessions() as session:
            result = await RoadmapService(session).detail(route_id, current)
        return {
            "id": result["id"],
            "title": result["title"],
            "description": result["description"],
            "difficulty": result["difficulty"],
            "url": f"/roadmaps/{result['id']}",
            "stages": [
                {
                    "title": stage["title"],
                    "nodes": [{"title": node["title"]} for node in stage["nodes"]],
                }
                for stage in result["stages"]
            ],
        }

    return [search_routes, get_route_detail]
