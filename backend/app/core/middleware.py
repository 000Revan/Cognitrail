"""通过纯 ASGI 中间件关联请求日志及错误响应。"""

from time import perf_counter
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send
from structlog.contextvars import bind_contextvars, reset_contextvars

from app.core.logging import get_logger

logger = get_logger(__name__)


class RequestContextMiddleware:
    """生成可信请求编号，并为包括 500 在内的响应附加编号。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        context_tokens = bind_contextvars(request_id=request_id)
        started = perf_counter()

        async def send_with_context(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                if not any(key.lower() == b"x-request-id" for key, _ in headers):
                    headers.append((b"x-request-id", request_id.encode()))
                if scope["path"].startswith("/api/v1/"):
                    headers.append((b"cache-control", b"no-store"))
                logger.info(
                    "http_request",
                    method=scope["method"],
                    path=scope["path"],
                    status=message["status"],
                    elapsed_ms=round((perf_counter() - started) * 1000, 1),
                )
            await send(message)

        try:
            await self.app(scope, receive, send_with_context)
        finally:
            reset_contextvars(**context_tokens)
