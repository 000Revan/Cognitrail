"""异步数据库资源：每请求独立会话，不自动提交业务事务。"""

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config.settings import Settings


class Database:
    """在应用生命周期内持有连接池，首次查询才连接数据库。"""

    def __init__(self, settings: Settings) -> None:
        self.engine: AsyncEngine = create_async_engine(
            settings.database_url,
            pool_pre_ping=True,
            pool_recycle=1800,
            connect_args={"connect_timeout": settings.db_connect_timeout},
            hide_parameters=True,
        )
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

        @event.listens_for(self.engine.sync_engine, "connect")
        def configure_connection(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("SET time_zone = '+00:00'")
                cursor.execute(
                    "SET SESSION sql_mode = "
                    "'STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION'"
                )
                cursor.execute("SET SESSION foreign_key_checks = 1")
            finally:
                cursor.close()

    async def close(self) -> None:
        """释放当前应用持有的连接池。"""
        await self.engine.dispose()


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """注入单请求会话；业务提交由 service 显式控制。"""
    async with request.app.state.database.sessions() as session:
        yield session
