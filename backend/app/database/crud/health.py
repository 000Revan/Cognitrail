"""健康检查所需只读数据库访问。"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def read_database_state(session: AsyncSession) -> dict:
    """一次检查连接、服务端配置及 Alembic 版本，不创建或修改表。"""
    row = (
        (
            await session.execute(
                text(
                    "SELECT VERSION() AS version, @@session.time_zone AS timezone, "
                    "@@session.sql_mode AS sql_mode, @@session.foreign_key_checks AS fk_checks"
                )
            )
        )
        .mappings()
        .one()
    )
    revision = (
        (await session.execute(text("SELECT version_num FROM alembic_version"))).scalars().all()
    )
    triggers = (
        (
            await session.execute(
                text(
                    "SELECT TRIGGER_NAME FROM information_schema.TRIGGERS "
                    "WHERE TRIGGER_SCHEMA = DATABASE()"
                )
            )
        )
        .scalars()
        .all()
    )
    return {**dict(row), "revisions": revision, "triggers": triggers}
