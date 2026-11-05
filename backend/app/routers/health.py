"""健康路由只注入依赖并调用服务。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_session
from app.schemas.common import ApiResponse
from app.schemas.health import LiveHealth, ReadyHealth
from app.services.health_service import HealthService

router = APIRouter(prefix="/health", tags=["健康检查"])


def get_health_service(request: Request) -> HealthService:
    """使用应用配置构造轻量服务。"""
    return HealthService(request.app.state.settings)


@router.get("/live", response_model=ApiResponse[LiveHealth])
async def live(service: Annotated[HealthService, Depends(get_health_service)]):
    """进程存活，不访问数据库。"""
    return ApiResponse(data=service.live())


@router.get("/ready", response_model=ApiResponse[ReadyHealth])
async def ready(
    service: Annotated[HealthService, Depends(get_health_service)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """数据库及迁移就绪；失败由全局处理器返回 503。"""
    return ApiResponse(data=await service.ready(session))
