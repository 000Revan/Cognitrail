"""举报人与管理员分别授权，所有写操作通过服务事务。"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_session
from app.dependencies.auth import CurrentUser, require_admin
from app.routers.v1.issues import check_posting
from app.schemas.common import ApiResponse, JsonId
from app.schemas.moderation import InvalidateCheckin, ReportCreate, ReportHandle
from app.services.auth_service import AuthContext
from app.services.moderation_service import ModerationService

router = APIRouter(tags=["举报与治理"])
Admin = Annotated[AuthContext, Depends(require_admin)]


def service(request: Request, session: Annotated[AsyncSession, Depends(get_session)]):
    """同一请求共用数据库会话及审计追踪标识。"""
    return ModerationService(session, request.state.request_id)


Service = Annotated[ModerationService, Depends(service)]
Status = Literal["pending", "processing", "resolved", "rejected"]


@router.post("/reports", response_model=ApiResponse[dict], status_code=201)
async def create(data: ReportCreate, current: CurrentUser, request: Request, service: Service):
    check_posting(request, current)
    return ApiResponse(code=201, data=await service.create(current.claims, data))


@router.get("/reports", response_model=ApiResponse[dict])
async def mine(
    current: CurrentUser,
    service: Service,
    status: Status | None = None,
    page: Annotated[int, Query(ge=1, le=1000000)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 20,
):
    return ApiResponse(data=await service.listing(current.claims, False, status, page, page_size))


@router.get("/admin/reports", response_model=ApiResponse[dict])
async def listing(
    current: Admin,
    service: Service,
    status: Status | None = None,
    page: Annotated[int, Query(ge=1, le=1000000)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 20,
):
    return ApiResponse(data=await service.listing(current.claims, True, status, page, page_size))


@router.get("/admin/reports/{report_id}", response_model=ApiResponse[dict])
async def detail(report_id: JsonId, current: Admin, service: Service):
    return ApiResponse(data=await service.detail(current.claims, report_id))


@router.patch("/admin/reports/{report_id}", response_model=ApiResponse[dict])
async def handle(report_id: JsonId, data: ReportHandle, current: Admin, service: Service):
    return ApiResponse(data=await service.handle(current.claims, report_id, data))


@router.post("/admin/checkins/{checkin_id}/invalidate", response_model=ApiResponse[dict])
async def invalidate(checkin_id: JsonId, data: InvalidateCheckin, current: Admin, service: Service):
    return ApiResponse(data=await service.invalidate_checkin(current.claims, checkin_id, data))
