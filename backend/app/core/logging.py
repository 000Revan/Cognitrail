"""应用日志统一入口；不主动记录请求体、连接串或凭证。"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog


def configure_logging(level: str = "INFO") -> None:
    """配置控制台输出；终端启用颜色，重定向时输出纯文本。"""
    log_level = _log_level(level)
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # 重复创建应用时复用本模块的 handler，不移除测试或宿主安装的 handler。
    handler = next(
        (item for item in root_logger.handlers if item.get_name() == "cognitrail.console"),
        None,
    )
    if handler is None:
        handler = logging.StreamHandler(sys.stdout)
        handler.set_name("cognitrail.console")
        root_logger.addHandler(handler)
    handler.setLevel(log_level)
    handler.setFormatter(logging.Formatter("%(message)s"))

    processors: list[Any] = [
        structlog.stdlib.filter_by_level,
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty()),
    ]
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # SQL 调试按需单独开启，避免 DEBUG 时输出大量业务查询。
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """获取模块日志器，业务上下文通过关键字参数传入。"""
    return structlog.get_logger(name)


def _log_level(level: str) -> int:
    """将字符串级别转换为 logging 常量，无效配置回退到 INFO。"""
    value = getattr(logging, level.strip().upper(), logging.INFO)
    return value if isinstance(value, int) else logging.INFO
