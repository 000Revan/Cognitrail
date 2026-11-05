"""将业务异常、请求校验错误及未知错误统一封装。"""

import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.core.exceptions import AppError
from app.schemas.common import ApiResponse, ErrorData

logger = logging.getLogger(__name__)


def error_response(request: Request, error: AppError) -> JSONResponse:
    """响应只包含安全字段，不包含异常对象或原始参数。"""
    payload = ApiResponse(
        code=error.status_code,
        msg=error.message,
        data=ErrorData(
            error_code=error.error_code,
            details=error.details,
            request_id=getattr(request.state, "request_id", "unknown"),
        ),
    )
    headers = {"X-Request-ID": payload.data.request_id}
    if error.status_code == 401:
        headers["WWW-Authenticate"] = "Bearer"
    if error.status_code == 429 and isinstance(error.details, dict):
        headers["Retry-After"] = str(error.details.get("retryAfterSeconds", 60))
    return JSONResponse(
        status_code=error.status_code,
        content=payload.model_dump(mode="json"),
        headers=headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局处理器，校验错误不回显可能含密码的 input 字段。"""

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, error: AppError) -> JSONResponse:
        return error_response(request, error)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, error: RequestValidationError) -> JSONResponse:
        details = [
            {"path": list(item["loc"]), "type": item["type"], "message": item["msg"]}
            for item in error.errors()
        ]
        malformed = any(item["type"] == "json_invalid" for item in error.errors())
        return error_response(
            request,
            AppError(
                400 if malformed else 422,
                "INVALID_JSON" if malformed else "VALIDATION_ERROR",
                "请求内容无法解析" if malformed else "请求字段校验失败",
                details,
            ),
        )

    @app.exception_handler(HTTPException)
    async def http_error_handler(request: Request, error: HTTPException) -> JSONResponse:
        response = error_response(
            request,
            AppError(
                error.status_code,
                f"HTTP_{error.status_code}",
                HTTPStatus(error.status_code).phrase,
            ),
        )
        response.headers.update(error.headers or {})
        return response

    @app.exception_handler(Exception)
    async def unexpected_handler(request: Request, error: Exception) -> JSONResponse:
        # 不输出异常字符串，避免驱动错误中携带连接参数。
        logger.error(
            "unexpected_error request_id=%s type=%s",
            getattr(request.state, "request_id", "unknown"),
            type(error).__name__,
        )
        return error_response(request, AppError(500, "INTERNAL_ERROR", "服务暂时不可用"))
