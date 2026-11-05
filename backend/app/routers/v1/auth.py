"""注册、登录和当前登录会话退出。"""

from fastapi import APIRouter, Depends

from app.dependencies.auth import AuthServiceDep, CurrentUser, check_login_rate
from app.schemas.auth import LoginRequest, LoginResponse, RegisterRequest
from app.schemas.common import ApiResponse
from app.schemas.user import UserPublic

router = APIRouter(prefix="/auth", tags=["账号认证"])


@router.post("/register", status_code=201, response_model=ApiResponse[UserPublic])
async def register(data: RegisterRequest, service: AuthServiceDep):
    """注册普通账号，不自动登录。"""
    return ApiResponse(code=201, msg="注册成功", data=await service.register(data))


@router.post(
    "/login", response_model=ApiResponse[LoginResponse], dependencies=[Depends(check_login_rate)]
)
async def login(data: LoginRequest, service: AuthServiceDep):
    """JSON 登录，返回仅供内存保存的访问凭证。"""
    return ApiResponse(msg="登录成功", data=await service.login(data))


@router.post("/logout", response_model=ApiResponse[None])
async def logout(current: CurrentUser, service: AuthServiceDep):
    """撤销当前会话；改密及停用会撤销全部会话。"""
    await service.logout(current.claims)
    return ApiResponse(msg="已退出登录", data=None)
