"""本人资料及独立鉴权的管理员账号接口。"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, Response

from app.config.enums import UserRole
from app.dependencies.auth import CurrentUser, require_admin
from app.dependencies.services import (
    get_avatar_store,
    get_enrollment_service,
    get_favorite_service,
    get_user_service,
)
from app.schemas.common import ApiResponse, JsonId, Page
from app.schemas.enrollment import EnrollmentPage, LearningOverview
from app.schemas.favorite import FavoritePage, PublicRoadmap
from app.schemas.user import (
    AccountCreate,
    AccountPasswordReset,
    AccountProfileUpdate,
    AccountStatus,
    AccountStatusUpdate,
    ActivitySummary,
    FollowPerson,
    FollowState,
    PasswordUpdate,
    PrivacySettings,
    PrivacyUpdate,
    ProfileUpdate,
    PublicIdentity,
    PublicProfile,
    UserPublic,
)
from app.services.auth_service import AuthContext
from app.services.avatar_service import AvatarStore
from app.services.enrollment_service import EnrollmentService
from app.services.favorite_service import FavoriteService
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["个人资料"])
UserServiceDep = Annotated[UserService, Depends(get_user_service)]
admin_router = APIRouter(prefix="/admin/users", tags=["账号管理"])
Admin = Annotated[AuthContext, Depends(require_admin)]
system_router = APIRouter(prefix="/admin/system", tags=["系统维护"])


@system_router.get("", response_model=ApiResponse[dict])
async def system_info(request: Request, current: Admin, service: UserServiceDep):
    return ApiResponse(data=await service.system_info(current.claims, request.app.state.settings))


@system_router.get("/audit-logs", response_model=ApiResponse[dict])
async def audit_logs(
    current: Admin,
    service: UserServiceDep,
    page: Annotated[int, Query(ge=1, le=1000000)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 20,
):
    return ApiResponse(data=await service.audit_listing(current.claims, page, page_size))


@router.post("/me/avatar", response_model=ApiResponse[UserPublic])
async def upload_avatar(request: Request, current: CurrentUser, service: UserServiceDep):
    """本人头像上传使用原始图片请求体，文件内容由服务层校验。"""
    return ApiResponse(
        msg="头像已更新", data=await service.update_avatar(current.claims, request.stream())
    )


@router.get("/{user_id}/profile", response_model=ApiResponse[PublicProfile])
async def public_profile(
    user_id: JsonId,
    current: CurrentUser,
    service: UserServiceDep,
    page: Annotated[int, Query(ge=1, le=1000000)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 12,
):
    return ApiResponse(data=await service.public_profile(current.claims, user_id, page, page_size))


@router.put("/{user_id}/follow", response_model=ApiResponse[FollowState])
async def follow(user_id: JsonId, current: CurrentUser, service: UserServiceDep):
    return ApiResponse(data=await service.follow(current.claims, user_id, True))


@router.delete("/{user_id}/follow", response_model=ApiResponse[FollowState])
async def unfollow(user_id: JsonId, current: CurrentUser, service: UserServiceDep):
    return ApiResponse(data=await service.follow(current.claims, user_id, False))


@router.get("/me/following", response_model=ApiResponse[Page[PublicIdentity]])
async def following(
    current: CurrentUser,
    service: UserServiceDep,
    page: Annotated[int, Query(ge=1, le=1000000)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 12,
):
    return ApiResponse(data=await service.following(current.claims, page, page_size))


@router.get("/{user_id}/following", response_model=ApiResponse[Page[FollowPerson]])
async def public_following(
    user_id: JsonId,
    current: CurrentUser,
    service: UserServiceDep,
    page: Annotated[int, Query(ge=1, le=1000000)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 12,
):
    return ApiResponse(
        data=await service.relationships(current.claims, user_id, "following", page, page_size)
    )


@router.get("/{user_id}/followers", response_model=ApiResponse[Page[FollowPerson]])
async def public_followers(
    user_id: JsonId,
    current: CurrentUser,
    service: UserServiceDep,
    page: Annotated[int, Query(ge=1, le=1000000)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 12,
):
    return ApiResponse(
        data=await service.relationships(current.claims, user_id, "followers", page, page_size)
    )


@router.get("/me/feed", response_model=ApiResponse[Page[ActivitySummary]])
async def feed(
    current: CurrentUser,
    service: UserServiceDep,
    page: Annotated[int, Query(ge=1, le=1000000)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 12,
):
    return ApiResponse(data=await service.activities(current.claims, page, page_size))


@router.get("/me/discussions", response_model=ApiResponse[dict])
async def discussions(
    current: CurrentUser,
    service: UserServiceDep,
    kind: Literal["questions", "replies"] = "questions",
    page: Annotated[int, Query(ge=1, le=1000000)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 12,
):
    return ApiResponse(data=await service.discussions(current.claims, kind, page, page_size))


@router.get("/{user_id}/activities", response_model=ApiResponse[Page[ActivitySummary]])
async def activities(
    user_id: JsonId,
    current: CurrentUser,
    service: UserServiceDep,
    page: Annotated[int, Query(ge=1, le=1000000)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 12,
):
    return ApiResponse(data=await service.activities(current.claims, page, page_size, user_id))


@router.get("/{user_id}/collections", response_model=ApiResponse[Page[PublicRoadmap]])
async def collections(
    user_id: JsonId,
    current: CurrentUser,
    service: UserServiceDep,
    category: Literal["favorite", "learning"],
    page: Annotated[int, Query(ge=1, le=1000000)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 12,
):
    return ApiResponse(
        data=await service.collections(current.claims, user_id, category, page, page_size)
    )


@router.get("/avatars/{filename}")
async def avatar(filename: str, store: Annotated[AvatarStore, Depends(get_avatar_store)]):
    """头像可在公开账号资料中展示，不暴露存储路径。"""
    return Response(
        await store.read(filename),
        media_type="image/png",
        headers={"X-Content-Type-Options": "nosniff"},
    )


@admin_router.post("", status_code=201, response_model=ApiResponse[UserPublic])
async def create_account(data: AccountCreate, current: Admin, service: UserServiceDep):
    return ApiResponse(
        code=201, msg="账号已创建", data=await service.create_account(current.claims, data)
    )


@admin_router.patch("/{user_id}", response_model=ApiResponse[UserPublic])
async def edit_account(
    user_id: JsonId,
    data: AccountProfileUpdate,
    current: Admin,
    service: UserServiceDep,
):
    return ApiResponse(data=await service.edit_account(current.claims, user_id, data))


@admin_router.post("/{user_id}/reset-password", response_model=ApiResponse[None])
async def reset_password(
    user_id: JsonId,
    data: AccountPasswordReset,
    current: Admin,
    service: UserServiceDep,
):
    await service.reset_account_password(current.claims, user_id, data)
    return ApiResponse(msg="密码已重置，旧登录凭证已失效", data=None)


@admin_router.get("", response_model=ApiResponse[Page[UserPublic]])
async def accounts(
    current: Admin,
    service: UserServiceDep,
    keyword: Annotated[str, Query(max_length=200)] = "",
    role: UserRole | None = None,
    status: AccountStatus | None = None,
    page: Annotated[int, Query(ge=1, le=1000000)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 20,
):
    return ApiResponse(
        data=await service.accounts(current.claims, keyword, role, status, page, page_size)
    )


@admin_router.patch("/{user_id}/status", response_model=ApiResponse[UserPublic])
async def account_status(
    user_id: JsonId,
    data: AccountStatusUpdate,
    current: Admin,
    service: UserServiceDep,
):
    return ApiResponse(data=await service.set_account_status(current.claims, user_id, data))


@router.get("/me/learning-overview", response_model=ApiResponse[LearningOverview])
async def learning_overview(
    current: CurrentUser,
    service: Annotated[EnrollmentService, Depends(get_enrollment_service)],
    month: Annotated[str | None, Query(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")] = None,
):
    return ApiResponse(data=await service.overview(current, month))


@router.get("/me/enrollments", response_model=ApiResponse[EnrollmentPage])
async def enrollments(
    current: CurrentUser,
    service: Annotated[EnrollmentService, Depends(get_enrollment_service)],
    status: Literal["active", "abandoned"] | None = None,
    page: Annotated[int, Query(ge=1, le=1000000)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 12,
):
    return ApiResponse(data=await service.listing(current, status, page, page_size))


@router.get("/me/favorites", response_model=ApiResponse[FavoritePage])
async def favorites(
    current: CurrentUser,
    service: Annotated[FavoriteService, Depends(get_favorite_service)],
    page: Annotated[int, Query(ge=1, le=1000000)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 12,
):
    return ApiResponse(data=await service.listing(current, page, page_size))


@router.get("/me", response_model=ApiResponse[UserPublic])
async def me(current: CurrentUser):
    return ApiResponse(data=current.user)


@router.patch("/me", response_model=ApiResponse[UserPublic])
async def update_me(data: ProfileUpdate, current: CurrentUser, service: UserServiceDep):
    return ApiResponse(
        msg="个人资料已更新", data=await service.update_profile(current.claims, data)
    )


@router.patch("/me/password", response_model=ApiResponse[None])
async def change_password(data: PasswordUpdate, current: CurrentUser, service: UserServiceDep):
    await service.change_password(current.claims, data)
    return ApiResponse(msg="密码已修改，请重新登录", data=None)


@router.get("/me/privacy", response_model=ApiResponse[PrivacySettings])
async def privacy(current: CurrentUser, service: UserServiceDep):
    """仅返回本人五项当前公开范围。"""
    return ApiResponse(data=await service.privacy(current.claims))


@router.patch("/me/privacy", response_model=ApiResponse[PrivacySettings])
async def update_privacy(data: PrivacyUpdate, current: CurrentUser, service: UserServiceDep):
    """设置版本冲突统一409，不静默覆盖其他页面的更新。"""
    return ApiResponse(
        msg="隐私设置已保存", data=await service.update_privacy(current.claims, data)
    )
