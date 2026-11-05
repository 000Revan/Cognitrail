"""业务异常不依赖 HTTP 路由。"""

from typing import Any


class AppError(Exception):
    """可安全呈现给客户端的错误。"""

    def __init__(
        self,
        status_code: int,
        error_code: str,
        message: str,
        details: dict[str, Any] | list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.details = details
