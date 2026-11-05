"""R05 本人学习接口，不提供旧笔记、收获及打卡改删。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.dependencies.auth import CurrentUser
from app.dependencies.services import get_enrollment_service
from app.schemas.common import ApiResponse, JsonId
from app.schemas.enrollment import (
    EnrollmentContent,
    EnrollmentPage,
    EnrollmentSummary,
    NodeStatusUpdate,
    PositionUpdate,
    SessionWrite,
    StudyRecordCreate,
    StudyRecordPage,
    StudyRecordResult,
    UpdatePrompt,
    UpgradePreview,
    UpgradeRequest,
    UpgradeResult,
)
from app.services.enrollment_service import EnrollmentService

router = APIRouter(prefix="/enrollments", tags=["路线学习"])
Service = Annotated[EnrollmentService, Depends(get_enrollment_service)]


@router.put("/{enrollment_id}/update-prompt", response_model=ApiResponse[EnrollmentSummary])
async def update_prompt(
    enrollment_id: JsonId, data: UpdatePrompt, current: CurrentUser, service: Service
):
    return ApiResponse(data=await service.dismiss_update(enrollment_id, current.claims, data))


@router.get("/{enrollment_id}", response_model=ApiResponse[EnrollmentSummary])
async def detail(
    enrollment_id: JsonId,
    current: CurrentUser,
    service: Service,
    session_id: Annotated[JsonId | None, Query(alias="sessionId")] = None,
):
    return ApiResponse(data=await service.detail(enrollment_id, current.claims, session_id))


@router.get("/{enrollment_id}/content", response_model=ApiResponse[EnrollmentContent])
async def content(
    enrollment_id: JsonId,
    current: CurrentUser,
    service: Service,
    session_id: Annotated[JsonId | None, Query(alias="sessionId")] = None,
):
    return ApiResponse(data=await service.content(enrollment_id, current.claims, session_id))


@router.get("/{enrollment_id}/upgrade/preview", response_model=ApiResponse[UpgradePreview])
async def upgrade_preview(enrollment_id: JsonId, current: CurrentUser, service: Service):
    return ApiResponse(data=await service.upgrade_preview(enrollment_id, current.claims))


@router.post("/{enrollment_id}/upgrade", response_model=ApiResponse[UpgradeResult])
async def upgrade(
    enrollment_id: JsonId, data: UpgradeRequest, current: CurrentUser, service: Service
):
    return ApiResponse(data=await service.upgrade(enrollment_id, current.claims, data))


@router.get("/{enrollment_id}/sessions", response_model=ApiResponse[EnrollmentPage])
async def sessions(
    enrollment_id: JsonId,
    current: CurrentUser,
    service: Service,
    page: Annotated[int, Query(ge=1, le=1000000)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 20,
):
    return ApiResponse(data=await service.sessions(enrollment_id, current.claims, page, page_size))


@router.patch("/{enrollment_id}/position", response_model=ApiResponse[EnrollmentSummary])
async def position(
    enrollment_id: JsonId, data: PositionUpdate, current: CurrentUser, service: Service
):
    return ApiResponse(data=await service.position(enrollment_id, current.claims, data))


@router.put(
    "/{enrollment_id}/nodes/{node_id}/status", response_model=ApiResponse[EnrollmentSummary]
)
async def status(
    enrollment_id: JsonId,
    node_id: JsonId,
    data: NodeStatusUpdate,
    current: CurrentUser,
    service: Service,
):
    return ApiResponse(data=await service.update_node(enrollment_id, node_id, current.claims, data))


@router.post("/{enrollment_id}/abandon", response_model=ApiResponse[EnrollmentSummary])
async def abandon(
    enrollment_id: JsonId, data: SessionWrite, current: CurrentUser, service: Service
):
    return ApiResponse(
        data=await service.transition(enrollment_id, current.claims, "abandon", data)
    )


@router.post("/{enrollment_id}/restore", response_model=ApiResponse[EnrollmentSummary])
async def restore(
    enrollment_id: JsonId, data: SessionWrite, current: CurrentUser, service: Service
):
    return ApiResponse(
        data=await service.transition(enrollment_id, current.claims, "restore", data)
    )


@router.post("/{enrollment_id}/records", response_model=ApiResponse[StudyRecordResult])
async def checkin(
    enrollment_id: JsonId, data: StudyRecordCreate, current: CurrentUser, service: Service
):
    return ApiResponse(data=await service.create_record(enrollment_id, current.claims, data))


@router.get("/{enrollment_id}/records", response_model=ApiResponse[StudyRecordPage])
async def records(
    enrollment_id: JsonId,
    current: CurrentUser,
    service: Service,
    page: Annotated[int, Query(ge=1, le=1000000)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 20,
):
    return ApiResponse(data=await service.records(enrollment_id, current.claims, page, page_size))


@router.put("/{enrollment_id}/resources/{resource_id}/visit")
async def visit_resource(
    enrollment_id: JsonId,
    resource_id: JsonId,
    data: SessionWrite,
    current: CurrentUser,
    service: Service,
):
    return ApiResponse(
        data=await service.visit_resource(enrollment_id, resource_id, current.claims, data)
    )
