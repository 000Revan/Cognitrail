"""路线内话题和回复；所有读写均要求登录。"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request

from app.core.exceptions import AppError
from app.dependencies.auth import CurrentUser
from app.dependencies.services import get_issue_service
from app.schemas.common import ApiResponse, JsonId
from app.schemas.issue import (
    CommentCreate,
    CommentEdit,
    IssueCreate,
    IssueEdit,
    IssueState,
    Status,
    SubscriptionChange,
)
from app.services.issue_service import IssueService

router = APIRouter(prefix="/roadmaps/{route_id}/issues", tags=["路线话题"])
Service = Annotated[IssueService, Depends(get_issue_service)]


def check_posting(request, current):
    """按真实连接IP和登录用户分别限流，不信任转发头。"""
    try:
        request.app.state.discussion_user_limiter.check(str(current.user.id))
        request.app.state.discussion_ip_limiter.check(
            request.client.host if request.client else "unknown"
        )
    except AppError as exc:
        raise AppError(
            429, "DISCUSSION_RATE_LIMITED", "发言过于频繁，请稍后再试", exc.details
        ) from exc


@router.get("", response_model=ApiResponse[dict])
async def listing(
    route_id: JsonId,
    current: CurrentUser,
    service: Service,
    status: Status | None = None,
    sort_by: Annotated[Literal["createdAt", "lastActivityAt"], Query(alias="sortBy")] = "createdAt",
    order: Literal["asc", "desc"] = "desc",
    page: Annotated[int, Query(ge=1, le=1000000)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 20,
):
    return ApiResponse(
        data=await service.listing(
            route_id, current.claims, status, page, page_size, sort_by, order
        )
    )


@router.post("", status_code=201, response_model=ApiResponse[dict])
async def create(
    route_id: JsonId, data: IssueCreate, current: CurrentUser, service: Service, request: Request
):
    check_posting(request, current)
    return ApiResponse(code=201, data=await service.create(route_id, current.claims, data))


@router.get("/{issue_id}", response_model=ApiResponse[dict])
async def detail(
    route_id: JsonId,
    issue_id: JsonId,
    current: CurrentUser,
    service: Service,
    page: Annotated[int, Query(ge=1, le=1000000)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 20,
    comment_id: Annotated[JsonId | None, Query(alias="commentId")] = None,
):
    return ApiResponse(
        data=await service.detail(route_id, issue_id, current.claims, page, page_size, comment_id)
    )


@router.patch("/{issue_id}", response_model=ApiResponse[dict])
async def edit(
    route_id: JsonId, issue_id: JsonId, data: IssueEdit, current: CurrentUser, service: Service
):
    return ApiResponse(data=await service.change(route_id, issue_id, current.claims, "edit", data))


@router.get("/{issue_id}/comments/{comment_id}/replies", response_model=ApiResponse[dict])
async def replies(
    route_id: JsonId,
    issue_id: JsonId,
    comment_id: JsonId,
    current: CurrentUser,
    service: Service,
    page: Annotated[int, Query(ge=1, le=1000000)] = 1,
):
    return ApiResponse(
        data=await service.replies(route_id, issue_id, comment_id, current.claims, page)
    )


@router.delete("/{issue_id}", response_model=ApiResponse[dict])
async def delete(route_id: JsonId, issue_id: JsonId, current: CurrentUser, service: Service):
    return ApiResponse(data=await service.change(route_id, issue_id, current.claims, "delete"))


@router.patch("/{issue_id}/state", response_model=ApiResponse[dict])
async def state(
    route_id: JsonId, issue_id: JsonId, data: IssueState, current: CurrentUser, service: Service
):
    return ApiResponse(data=await service.change(route_id, issue_id, current.claims, "state", data))


@router.put("/{issue_id}/subscription", response_model=ApiResponse[dict])
async def subscription(
    route_id: JsonId,
    issue_id: JsonId,
    data: SubscriptionChange,
    current: CurrentUser,
    service: Service,
):
    return ApiResponse(
        data=await service.change(route_id, issue_id, current.claims, "subscription", data)
    )


@router.post("/{issue_id}/comments", status_code=201, response_model=ApiResponse[dict])
async def comment(
    route_id: JsonId,
    issue_id: JsonId,
    data: CommentCreate,
    current: CurrentUser,
    service: Service,
    request: Request,
):
    check_posting(request, current)
    return ApiResponse(
        code=201, data=await service.change(route_id, issue_id, current.claims, "comment", data)
    )


@router.patch("/{issue_id}/comments/{comment_id}", response_model=ApiResponse[dict])
async def edit_comment(
    route_id: JsonId,
    issue_id: JsonId,
    comment_id: JsonId,
    data: CommentEdit,
    current: CurrentUser,
    service: Service,
):
    return ApiResponse(
        data=await service.change(
            route_id, issue_id, current.claims, "edit_comment", data, comment_id
        )
    )


@router.delete("/{issue_id}/comments/{comment_id}", response_model=ApiResponse[dict])
async def delete_comment(
    route_id: JsonId, issue_id: JsonId, comment_id: JsonId, current: CurrentUser, service: Service
):
    return ApiResponse(
        data=await service.change(
            route_id, issue_id, current.claims, "delete_comment", comment_id=comment_id
        )
    )
