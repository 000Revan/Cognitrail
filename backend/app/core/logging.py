"""日志仅记录请求路径和状态，不记录请求体、连接串或凭证。"""

import logging


def configure_logging(level: str) -> None:
    """配置应用日志；数据库 SQL 参数默认不输出。"""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
