"""消息中心：本人列表、未读、已读及安全目标定位。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.dependencies.auth import CurrentUser
from app.dependencies.services import get_notification_service
from app.schemas.common import ApiResponse, JsonId
from app.schemas.issue import DeleteNotifications, ReadNotifications
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["站内消息"])
Service = Annotated[NotificationService, Depends(get_notification_service)]


@router.get("", response_model=ApiResponse[dict])
async def listing(
    current: CurrentUser,
    service: Service,
    unread: bool = False,
    page: Annotated[int, Query(ge=1, le=1000000)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 20,
):
    return ApiResponse(data=await service.listing(current.claims, page, page_size, unread))


@router.get("/unread-count", response_model=ApiResponse[dict])
async def unread(current: CurrentUser, service: Service):
    return ApiResponse(data=await service.unread(current.claims))


@router.patch("/read", response_model=ApiResponse[dict])
async def read_all(data: ReadNotifications, current: CurrentUser, service: Service):
    return ApiResponse(data=await service.read(current.claims, through_id=data.through_id))


@router.delete("", response_model=ApiResponse[dict])
async def delete_many(data: DeleteNotifications, current: CurrentUser, service: Service):
    return ApiResponse(
        data=await service.delete(
            current.claims, through_id=data.through_id, read_only=data.read_only
        )
    )


@router.delete("/{notification_id}", response_model=ApiResponse[dict])
async def delete_one(notification_id: JsonId, current: CurrentUser, service: Service):
    return ApiResponse(data=await service.delete(current.claims, notification_id=notification_id))


@router.patch("/{notification_id}/read", response_model=ApiResponse[dict])
async def read(notification_id: JsonId, current: CurrentUser, service: Service):
    return ApiResponse(data=await service.read(current.claims, notification_id=notification_id))


@router.get("/{notification_id}/target", response_model=ApiResponse[dict])
async def target(notification_id: JsonId, current: CurrentUser, service: Service):
    return ApiResponse(data=await service.target(current.claims, notification_id))
