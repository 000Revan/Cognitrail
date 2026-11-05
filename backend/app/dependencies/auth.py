"""Bearer 凭证及数据库身份校验。"""

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config.enums import UserRole
from app.core.exceptions import AppError
from app.core.security import unauthorized
from app.dependencies.services import get_auth_service
from app.services.auth_service import AuthContext, AuthService

bearer = HTTPBearer(auto_error=False)
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    service: AuthServiceDep,
) -> AuthContext:
    """缺失凭证也返回统一 401，不泄露 JWT 校验细节。"""
    if credentials is None:
        raise unauthorized()
    current = await service.authenticate(service.tokens.decode(credentials.credentials))
    path = request.url.path
    template = request.scope["route"].path.removeprefix("/api/v1")
    account_paths = {"/api/v1/users/me", "/api/v1/users/me/avatar", "/api/v1/users/me/password"}
    official_templates = {
        "/roadmaps",
        "/roadmaps/{route_id}/draft",
        "/roadmaps/{route_id}/validate",
        "/roadmaps/{route_id}/publish",
        "/roadmaps/{route_id}/archive",
        "/roadmaps/{route_id}/restore",
        "/roadmaps/{route_id}",
    }
    official = (
        template in official_templates and request.method != "GET"
    ) or template == "/roadmaps/{route_id}/draft"
    if current.user.role == UserRole.ADMIN and not (
        path.startswith("/api/v1/admin/")
        or path.startswith("/api/v1/auth/")
        or path in account_paths
        or official
    ):
        raise AppError(403, "ADMIN_COMMUNITY_FORBIDDEN", "管理账号不参与社区，请使用普通账号")
    return current


CurrentUser = Annotated[AuthContext, Depends(get_current_user)]


async def get_optional_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    service: AuthServiceDep,
) -> AuthContext | None:
    """公开详情允许匿名；携带凭证时仍按数据库校验，不能以伪造身份读取工作稿。"""
    if credentials is None:
        return None
    current = await service.authenticate(service.tokens.decode(credentials.credentials))
    official_preview = (
        request.scope["route"].path.removeprefix("/api/v1") == "/roadmaps/{route_id}"
        and request.query_params.get("preview") == "draft"
    )
    if current.user.role == UserRole.ADMIN and not official_preview:
        raise AppError(403, "ADMIN_COMMUNITY_FORBIDDEN", "请从管理后台审核内容")
    return current


async def require_admin(current: CurrentUser) -> AuthContext:
    """管理员能力供后续官方路线维护复用，角色来自数据库。"""
    if current.user.role != UserRole.ADMIN:
        raise AppError(403, "ADMIN_REQUIRED", "需要管理员权限")
    return current


def check_login_rate(request: Request) -> None:
    """来源使用 ASGI 解析的 client，不直接采信任意请求头。"""
    key = request.client.host if request.client else "unknown"
    request.app.state.login_limiter.check(key)
