"""S03作者仓库、共用结构详情与工作稿事务接口。"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.config.enums import Difficulty
from app.dependencies.auth import CurrentUser, get_optional_user, require_admin
from app.dependencies.services import (
    get_enrollment_service,
    get_favorite_service,
    get_roadmap_service,
)
from app.schemas.common import ApiResponse, JsonId
from app.schemas.enrollment import EnrollmentSummary, EnrollRequest
from app.schemas.favorite import FavoriteResult, PublicRoadmapPage
from app.schemas.issue import SubscriptionChange
from app.schemas.roadmap import (
    PublishAction,
    RoadmapCreate,
    RoadmapDisable,
    RoadmapSave,
    VersionAction,
)
from app.services.auth_service import AuthContext
from app.services.enrollment_service import EnrollmentService
from app.services.favorite_service import FavoriteService
from app.services.roadmap_service import RoadmapService

router = APIRouter(prefix="/roadmaps", tags=["路线创作"])
Service = Annotated[RoadmapService, Depends(get_roadmap_service)]
OptionalUser = Annotated[AuthContext | None, Depends(get_optional_user)]
Favorites = Annotated[FavoriteService, Depends(get_favorite_service)]
admin_router = APIRouter(prefix="/admin/roadmaps", tags=["官方内容与治理"])
official_router = APIRouter(prefix="/admin/official-roadmaps", tags=["官方路线"])
Admin = Annotated[AuthContext, Depends(require_admin)]


@router.get("/{route_id}/subscription", response_model=ApiResponse[SubscriptionChange])
async def subscription(route_id: JsonId, current: CurrentUser, service: Favorites):
    return ApiResponse(data=await service.subscription(route_id, current.claims))


@router.put("/{route_id}/subscription", response_model=ApiResponse[SubscriptionChange])
async def update_subscription(
    route_id: JsonId, data: SubscriptionChange, current: CurrentUser, service: Favorites
):
    return ApiResponse(data=await service.subscription(route_id, current.claims, data))


@official_router.get("", response_model=ApiResponse[dict])
async def official_list(
    current: Admin,
    service: Service,
    archived: bool = False,
    keyword: Annotated[str, Query(max_length=200)] = "",
    status: Literal["draft", "published", "archived", "disabled"] | None = None,
    page: Annotated[int, Query(ge=1, le=1000000)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 12,
):
    return ApiResponse(
        data=await service.official_listing(
            current.claims, archived, page, page_size, keyword, status
        )
    )


@admin_router.get("", response_model=ApiResponse[dict])
async def admin_list(
    current: Admin,
    service: Service,
    keyword: Annotated[str, Query(max_length=200)] = "",
    status: Literal["published", "archived", "disabled"] | None = None,
    difficulty: Difficulty | None = None,
    sort_by: Annotated[
        Literal["publishedAt", "updatedAt", "title"], Query(alias="sortBy")
    ] = "publishedAt",
    order: Literal["asc", "desc"] = "desc",
    page: Annotated[int, Query(ge=1, le=1000000)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 12,
):
    return ApiResponse(
        data=await service.admin_listing(
            current.claims, keyword, difficulty, status, sort_by, order, page, page_size
        )
    )


@admin_router.get("/{route_id}", response_model=ApiResponse[dict])
async def admin_detail(
    route_id: JsonId,
    current: Admin,
    service: Service,
    release_id: Annotated[JsonId | None, Query(alias="releaseId")] = None,
):
    return ApiResponse(data=await service.admin_detail(route_id, current.claims, release_id))


@admin_router.post("/{route_id}/disable", response_model=ApiResponse[dict])
async def disable(route_id: JsonId, data: RoadmapDisable, current: Admin, service: Service):
    return ApiResponse(data=await service.moderate(route_id, current.claims, data, "disable"))


@admin_router.post("/{route_id}/restore", response_model=ApiResponse[dict])
async def restore_content(route_id: JsonId, data: RoadmapDisable, current: Admin, service: Service):
    return ApiResponse(data=await service.moderate(route_id, current.claims, data, "restore"))


@router.post("/{route_id}/enroll", response_model=ApiResponse[EnrollmentSummary])
async def enroll(
    route_id: JsonId,
    data: EnrollRequest,
    current: CurrentUser,
    service: Annotated[EnrollmentService, Depends(get_enrollment_service)],
):
    return ApiResponse(data=await service.enroll(route_id, current.claims, data.release_id))


@router.get("", response_model=ApiResponse[PublicRoadmapPage])
async def community(
    service: Favorites,
    current: OptionalUser,
    q: Annotated[str, Query(max_length=200)] = "",
    difficulty: Difficulty | None = None,
    sort_by: Annotated[
        Literal["publishedAt", "learnerCount", "favoriteCount"], Query(alias="sortBy")
    ] = "publishedAt",
    order: Literal["asc", "desc"] = "desc",
    page: Annotated[int, Query(ge=1, le=1000000)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 12,
):
    return ApiResponse(
        data=await service.community(current, q, difficulty, page, page_size, sort_by, order)
    )


@router.put("/{route_id}/favorite", response_model=ApiResponse[FavoriteResult])
async def favorite(route_id: JsonId, current: CurrentUser, service: Favorites):
    return ApiResponse(data=await service.change(route_id, current.claims, True))


@router.delete("/{route_id}/favorite", response_model=ApiResponse[FavoriteResult])
async def unfavorite(route_id: JsonId, current: CurrentUser, service: Favorites):
    return ApiResponse(data=await service.change(route_id, current.claims, False))


@router.get("/mine", response_model=ApiResponse[dict])
async def mine(
    current: CurrentUser,
    service: Service,
    archived: bool = False,
    state: Literal["editing", "draft", "withdrawn", "published", "disabled"] | None = None,
    q: Annotated[str, Query(max_length=200)] = "",
    page: Annotated[int, Query(ge=1, le=1000000)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 12,
):
    return ApiResponse(data=await service.listing(current, archived, state, q, page, page_size))


@router.post("", status_code=201, response_model=ApiResponse[dict])
async def create(data: RoadmapCreate, current: CurrentUser, service: Service):
    return ApiResponse(code=201, data=await service.create(current.claims, data))


@router.get("/{route_id}", response_model=ApiResponse[dict])
async def detail(
    route_id: JsonId,
    service: Service,
    current: OptionalUser,
    enrollment_id: Annotated[JsonId | None, Query(alias="enrollmentId")] = None,
    preview: Literal["draft"] | None = None,
):
    return ApiResponse(data=await service.detail(route_id, current, enrollment_id, preview))


@router.get("/{route_id}/draft", response_model=ApiResponse[dict])
async def draft(route_id: JsonId, current: CurrentUser, service: Service):
    return ApiResponse(data=await service.draft(route_id, current.claims))


@router.put("/{route_id}/draft", response_model=ApiResponse[dict])
async def save(route_id: JsonId, data: RoadmapSave, current: CurrentUser, service: Service):
    return ApiResponse(data=await service.save(route_id, current.claims, data))


@router.post("/{route_id}/validate", response_model=ApiResponse[dict])
async def validate(route_id: JsonId, data: VersionAction, current: CurrentUser, service: Service):
    return ApiResponse(data=await service.validate(route_id, current.claims, data.expected_version))


@router.post("/{route_id}/publish", response_model=ApiResponse[dict])
async def publish(route_id: JsonId, data: PublishAction, current: CurrentUser, service: Service):
    return ApiResponse(
        data=await service.publish(
            route_id, current.claims, data.expected_version, data.update_summary
        )
    )


@router.post("/{route_id}/withdraw", response_model=ApiResponse[dict])
async def withdraw(route_id: JsonId, data: VersionAction, current: CurrentUser, service: Service):
    return ApiResponse(
        data=await service.transition(route_id, current.claims, data.expected_version, "withdraw")
    )


@router.post("/{route_id}/archive", response_model=ApiResponse[dict])
async def archive(route_id: JsonId, data: VersionAction, current: CurrentUser, service: Service):
    return ApiResponse(
        data=await service.transition(route_id, current.claims, data.expected_version, "archive")
    )


@router.post("/{route_id}/restore", response_model=ApiResponse[dict])
async def restore(route_id: JsonId, data: VersionAction, current: CurrentUser, service: Service):
    return ApiResponse(
        data=await service.transition(route_id, current.claims, data.expected_version, "restore")
    )


@router.delete("/{route_id}", response_model=ApiResponse[None])
async def delete(route_id: JsonId, data: VersionAction, current: CurrentUser, service: Service):
    await service.delete_draft(route_id, current.claims, data.expected_version)
    return ApiResponse(msg="草稿已永久删除", data=None)
