"""集中挂载业务 API。"""

from fastapi import APIRouter, Depends, Request

from app.core.exceptions import AppError
from app.database import validation
from app.routers.v1.auth import router as auth_router
from app.routers.v1.enrollments import router as enrollments_router
from app.routers.v1.issues import router as issues_router
from app.routers.v1.moderation import router as moderation_router
from app.routers.v1.notifications import router as notifications_router
from app.routers.v1.roadmaps import admin_router, official_router
from app.routers.v1.roadmaps import router as roadmaps_router
from app.routers.v1.users import admin_router as admin_users_router
from app.routers.v1.users import router as users_router
from app.routers.v1.users import system_router

API_PREFIX = "/api/v1"


def require_community_endpoint(request: Request) -> None:
    """先核对接口开放清单，再允许解析身份和获取业务数据库会话。"""
    path = request.scope["route"].path
    # 当前FastAPI挂载子路由时route.path不含父路由前缀；兼容完整模板形式。
    if not path.startswith(API_PREFIX + "/"):
        path = API_PREFIX + path
    endpoint = (request.method, path)
    if endpoint not in validation.COMMUNITY_ENABLED_ENDPOINTS:
        raise AppError(
            503,
            "COMMUNITY_FEATURE_NOT_READY",
            "公开社区正在升级，此功能暂未开放",
        )


router = APIRouter(prefix=API_PREFIX, dependencies=[Depends(require_community_endpoint)])
router.include_router(auth_router)
router.include_router(users_router)
router.include_router(roadmaps_router)
router.include_router(enrollments_router)
router.include_router(issues_router)
router.include_router(notifications_router)
router.include_router(admin_router)
router.include_router(official_router)
router.include_router(admin_users_router)
router.include_router(system_router)
router.include_router(moderation_router)
