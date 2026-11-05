"""应用工厂，后续业务路由统一挂载至 /api/v1。"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import Settings
from app.core.exception_handlers import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.core.rate_limit import LoginRateLimiter
from app.lifespan import lifespan
from app.routers.api import router as api_router
from app.routers.health import router as health_router


def create_app(settings: Settings | None = None) -> FastAPI:
    """组装基础设施，支持测试注入配置而不读取真实凭证。"""
    settings = settings or Settings()
    configure_logging(settings.log_level)
    application = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    application.state.settings = settings
    application.state.login_limiter = LoginRateLimiter(
        settings.login_rate_limit,
        settings.login_rate_window_seconds,
    )
    application.state.discussion_user_limiter = LoginRateLimiter(
        settings.discussion_user_rate_limit,
        settings.discussion_rate_window_seconds,
    )
    application.state.discussion_ip_limiter = LoginRateLimiter(
        settings.discussion_ip_rate_limit,
        settings.discussion_rate_window_seconds,
    )
    register_exception_handlers(application)
    application.include_router(health_router)
    application.include_router(api_router)
    application.add_middleware(RequestContextMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["X-Request-ID"],
    )
    return application


app = create_app()
