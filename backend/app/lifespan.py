"""启动 MySQL 连接池和 SQLite 检查点；不执行 MySQL 建表或迁移。"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

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
        checkpoint_path = app.state.settings.agent_checkpoint_path
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        async with AsyncSqliteSaver.from_conn_string(str(checkpoint_path)) as checkpointer:
            await checkpointer.setup()
            app.state.agent_checkpointer = checkpointer
            yield
    finally:
        if worker:
            worker.cancel()
            with suppress(asyncio.CancelledError):
                await worker
        await database.close()
