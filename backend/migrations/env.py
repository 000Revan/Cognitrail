"""MySQL 异步迁移环境：不将密码写入配置文件或日志。"""

import asyncio

from alembic import context
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from app.config.settings import Settings
from app.database import models  # noqa: F401
from app.database.base import Base
from app.database.session import Database

# 冻结迁移只负责首次建库及旧库预检；结构比较以当前31表业务ORM为准。
baseline = ScriptDirectory.from_config(context.config).get_revision("c001_community").module
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """生成 SQL 无需连接数据库；仍固定使用 MySQL 方言。"""
    context.configure(
        url="mysql+asyncmy://",
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def migrate(connection) -> None:
    """迁移前拒绝旧库、半成品与错误版本，不自动建库或stamp旧历史。"""
    settings = Settings()
    version = connection.execute(text("SELECT VERSION()")).scalar_one()
    if version.split("-")[0] != settings.db_required_version:
        raise RuntimeError(
            f"MySQL 版本不符：需要 {settings.db_required_version}，实际 {version}；未执行迁移"
        )
    tables = set(inspect(connection).get_table_names())
    revisions = (
        connection.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
        if "alembic_version" in tables
        else []
    )
    if revisions in (
        ["c002_notification_delete"],
        ["c003_official_roadmaps"],
        ["c004_topic_privacy"],
    ):
        # 复用冻结基线的完整表集合校验，增量版本另外核对新增列。
        baseline.validate_database_state(tables, [baseline.revision])
        columns = {column["name"] for column in inspect(connection).get_columns("notifications")}
        if "deleted_at" not in columns:
            raise RuntimeError("通知删除迁移版本与实际列不一致，未执行迁移")
        if revisions in (["c003_official_roadmaps"], ["c004_topic_privacy"]):
            route_columns = {c["name"] for c in inspect(connection).get_columns("skill_roadmaps")}
            if "roadmap_type" not in route_columns:
                raise RuntimeError("官方路线迁移版本与实际列不一致，未执行迁移")
        if revisions == ["c004_topic_privacy"]:
            privacy_columns = {
                c["name"] for c in inspect(connection).get_columns("user_privacy_settings")
            }
            if "topic_public" not in privacy_columns:
                raise RuntimeError("话题隐私迁移版本与实际列不一致，未执行迁移")
    else:
        baseline.validate_database_state(tables, revisions)
    # 版本查询触发 autobegin，需结束该只读事务再交给 Alembic。
    connection.commit()
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    settings = Settings()
    database = Database(settings)
    try:
        async with database.engine.connect() as connection:
            await connection.run_sync(migrate)
    finally:
        await database.close()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
