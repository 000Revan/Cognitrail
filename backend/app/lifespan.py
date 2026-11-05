"""应用启动不隐式建表或执行迁移。"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app.database.session import Database
from app.services.notification_service import OutboxDispatcher


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """启动连接池并在关闭时释放；断库时仍允许 live 返回。"""
    database = Database(app.state.settings)
    app.state.database = database
    worker = (
        asyncio.create_task(OutboxDispatcher(database, app.state.settings).run())
        if app.state.settings.outbox_enabled
        else None
    )
    try:
        yield
    finally:
        if worker:
            worker.cancel()
            with suppress(asyncio.CancelledError):
                await worker
        await database.close()
