"""进程存活与数据库就绪分离，数据库故障不阻止进程启动。"""

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import BACKEND_ROOT, Settings
from app.core.exceptions import AppError
from app.database.crud.health import read_database_state
from app.database.validation import COMMUNITY_APPLICATION_READY, EXPECTED_TRIGGERS
from app.schemas.health import LiveHealth, ReadyHealth


def migration_heads() -> set[str]:
    """从迁移文件读取期望版本，避免重复硬编码当前 head。"""
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(Path(BACKEND_ROOT / "migrations")))
    return set(ScriptDirectory.from_config(config).get_heads())


class HealthService:
    """提供不包含连接信息或 SQL 的健康结果。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def live(self) -> LiveHealth:
        """仅检查当前进程，不访问数据库。"""
        return LiveHealth(service=self.settings.app_name, checked_at=datetime.now(UTC))

    async def ready(self, session: AsyncSession) -> ReadyHealth:
        """必须连接成功、环境正确并完成最新迁移才能返回 200。"""
        try:
            async with asyncio.timeout(self.settings.db_connect_timeout + 2):
                state = await read_database_state(session)
        except (SQLAlchemyError, OSError, TimeoutError) as error:
            raise AppError(503, "DATABASE_NOT_READY", "数据库未就绪，请检查连接与迁移") from error
        if state["version"].split("-")[0] != self.settings.db_required_version:
            raise AppError(503, "DATABASE_VERSION_MISMATCH", "数据库版本不符合项目基线")
        if (
            state["timezone"] != "+00:00"
            or state["fk_checks"] != 1
            or "STRICT_TRANS_TABLES" not in state["sql_mode"]
        ):
            raise AppError(503, "DATABASE_CONFIGURATION_MISMATCH", "数据库会话配置不符合基线")
        if set(state["revisions"]) != migration_heads():
            raise AppError(503, "MIGRATION_REQUIRED", "数据库迁移版本不是最新版本")
        if not EXPECTED_TRIGGERS.issubset(set(state["triggers"])):
            raise AppError(503, "DATABASE_VALIDATION_MISSING", "数据库校验触发器不完整")
        if not COMMUNITY_APPLICATION_READY:
            raise AppError(
                503,
                "COMMUNITY_REFACTOR_PENDING",
                "账号、创作、发现、学习及路线讨论已逐步开放，作者主页与路线治理仍待适配，整体业务尚未就绪",
            )
        return ReadyHealth(
            database_version=state["version"],
            migration_revision=state["revisions"][0],
            timezone=self.settings.app_timezone,
            checked_at=datetime.now(UTC),
        )
