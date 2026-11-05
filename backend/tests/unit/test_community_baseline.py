"""社区基线离线契约，以及显式独立测试库中的真实约束验证。"""

import os
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import StringIO
from uuid import uuid4

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Integer, PrimaryKeyConstraint, UniqueConstraint, insert, select, text, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.sqltypes import Numeric

from app.config.settings import BACKEND_ROOT
from app.database import models  # noqa: F401
from app.database.base import Base
from app.database.validation import EXPECTED_TRIGGERS, VALIDATED_TABLES

REVISION = "c001_community"
HEAD = "c005_resource_visits"
TABLES = {
    "users",
    "user_auth_sessions",
    "user_privacy_settings",
    "user_follows",
    "skill_roadmaps",
    "roadmap_stages",
    "learning_nodes",
    "node_resources",
    "roadmap_stage_edges",
    "roadmap_releases",
    "release_stages",
    "release_nodes",
    "release_resources",
    "release_stage_edges",
    "roadmap_favorites",
    "user_roadmaps",
    "learning_sessions",
    "user_node_progress",
    "learning_session_events",
    "roadmap_checkins",
    "roadmap_issues",
    "issue_comments",
    "issue_subscriptions",
    "issue_events",
    "roadmap_subscriptions",
    "activity_events",
    "notification_outbox",
    "notifications",
    "content_reports",
    "moderation_actions",
    "audit_logs",
}


def config(output=None):
    return Config(str(BACKEND_ROOT / "alembic.ini"), output_buffer=output)


def baseline():
    script = ScriptDirectory.from_config(config())
    assert script.get_heads() == [HEAD]
    assert len(list(script.walk_revisions())) == 5
    return script.get_revision(REVISION).module


def test_notification_delete_incremental_sql_preserves_existing_messages():
    output = StringIO()
    command.upgrade(config(output), REVISION + ":c004_topic_privacy", sql=True)
    sql = output.getvalue()
    assert "ALTER TABLE notifications ADD COLUMN deleted_at DATETIME(6)" in sql
    assert "CREATE TABLE" not in sql
    assert "DELETE FROM" not in sql
    assert "UPDATE notifications" not in sql


def test_topic_privacy_incremental_migration_is_additive_and_default_private():
    output = StringIO()
    command.upgrade(config(output), "c003_official_roadmaps:" + HEAD, sql=True)
    sql = output.getvalue()
    assert "ALTER TABLE user_privacy_settings ADD COLUMN topic_public TINYINT UNSIGNED" in sql
    assert "DEFAULT 0" in sql and sql.count("CREATE TRIGGER ") == 2
    assert "UPDATE user_privacy_settings" not in sql and "DELETE FROM" not in sql
    assert "DROP TABLE" not in sql


@pytest.mark.database
@pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="需显式独立测试库")
@pytest.mark.parametrize("operation", ["insert", "update"])
async def test_topic_privacy_trigger_rejects_non_boolean(
    community_session, community_rows, operation
):
    table = Base.metadata.tables["user_privacy_settings"]
    uid = community_rows["users"]["id"]
    statement = (
        insert(table).values(user_id=uid, topic_public=2)
        if operation == "insert"
        else update(table).where(table.c.user_id == uid).values(topic_public=2)
    )
    with pytest.raises((IntegrityError, OperationalError)) as caught:
        async with community_session.begin_nested():
            await community_session.execute(statement)
    assert caught.value.orig.args[0] == 1644
    assert (
        await community_session.scalar(select(table.c.topic_public).where(table.c.user_id == uid))
        == 0
    )


def test_official_route_incremental_sql_preserves_existing_community_ownership():
    output = StringIO()
    command.upgrade(config(output), "c002_notification_delete:" + HEAD, sql=True)
    sql = output.getvalue()
    assert "ALTER TABLE skill_roadmaps ADD COLUMN roadmap_type ENUM('user','official')" in sql
    assert "DEFAULT 'user'" in sql
    assert "DROP TABLE" not in sql and "UPDATE skill_roadmaps" not in sql


@pytest.mark.parametrize("offline", [True, False])
def test_official_route_downgrade_refuses_loss_of_official_ownership(monkeypatch, offline):
    from types import SimpleNamespace
    from unittest.mock import Mock

    migration = ScriptDirectory.from_config(config()).get_revision("c003_official_roadmaps").module
    drop = Mock()
    monkeypatch.setattr(migration.context, "is_offline_mode", lambda: offline)
    monkeypatch.setattr(migration.op, "drop_column", drop)
    monkeypatch.setattr(
        migration.op,
        "get_bind",
        lambda: SimpleNamespace(execute=lambda _: SimpleNamespace(scalar_one=lambda: 1)),
    )
    with pytest.raises(RuntimeError):
        migration.downgrade()
    drop.assert_not_called()


@pytest.mark.parametrize("offline", [True, False])
def test_notification_delete_downgrade_refuses_to_restore_deleted_history(monkeypatch, offline):
    from types import SimpleNamespace
    from unittest.mock import Mock

    migration = (
        ScriptDirectory.from_config(config()).get_revision("c002_notification_delete").module
    )
    drop = Mock()
    monkeypatch.setattr(migration.context, "is_offline_mode", lambda: offline)
    monkeypatch.setattr(migration.op, "drop_column", drop)
    monkeypatch.setattr(
        migration.op,
        "get_bind",
        lambda: SimpleNamespace(execute=lambda _: SimpleNamespace(scalar_one=lambda: 1)),
    )
    with pytest.raises(RuntimeError):
        migration.downgrade()
    drop.assert_not_called()


def test_only_new_initial_revision_and_31_documented_tables():
    """清理旧历史，首版没有标签、笔记或旧版学习关系字段。"""
    migration = baseline()
    assert migration.down_revision is None
    assert set(migration.metadata.tables) == TABLES
    assert set(VALIDATED_TABLES) == TABLES
    assert EXPECTED_TRIGGERS == {
        f"{prefix}_{name}_validate" for name in migration.TRIGGER_RULES for prefix in ("bi", "bu")
    } | {f"{prefix}_user_privacy_settings_topic" for prefix in ("bi", "bu")}
    assert not (BACKEND_ROOT / "scripts/init_database.py").exists()
    tables = migration.metadata.tables
    assert "release_id" not in tables["user_roadmaps"].c
    assert "current_session_id" in tables["user_roadmaps"].c
    assert not {"release_id", "release_node_id", "issue_type"} & set(
        tables["roadmap_issues"].c.keys()
    )
    assert not {"target_audience", "prerequisites", "learning_goals", "draft_tags"} & set(
        tables["skill_roadmaps"].c.keys()
    )
    assert tables["skill_roadmaps"].c.effort_note.nullable
    assert tables["release_nodes"].c.estimated_minutes.nullable


def test_foreign_keys_have_unique_targets_and_explicit_indexes():
    """逐个复核同版/同关系外键及候选键，避免仅检查单列存在。"""
    for table in baseline().metadata.tables.values():
        for fk in table.foreign_key_constraints:
            local = tuple(e.parent.name for e in fk.elements)
            remote = tuple(e.column.name for e in fk.elements)
            parent = fk.referred_table
            keys = [
                tuple(c.name for c in key.columns)
                for key in parent.constraints
                if isinstance(key, PrimaryKeyConstraint | UniqueConstraint)
            ]
            assert remote in keys, (table.name, local, parent.name, remote)
            indexes = [
                tuple(c.name for c in key.columns)
                for key in table.constraints
                if isinstance(key, PrimaryKeyConstraint | UniqueConstraint)
            ]
            indexes += [tuple(c.name for c in index.columns) for index in table.indexes]
            assert any(cols[: len(local)] == local for cols in indexes), (table.name, local)
            assert fk.ondelete == "RESTRICT" and fk.onupdate == "RESTRICT"
        for column in table.c:
            if isinstance(column.type, Integer):
                assert column.type.unsigned, (table.name, column.name)
    tables = baseline().metadata.tables
    for name in ("release_stages", "release_nodes", "release_resources", "release_stage_edges"):
        assert not any(
            fk.referred_table.name in {"roadmap_stages", "learning_nodes", "node_resources"}
            for fk in tables[name].foreign_key_constraints
        )


def test_offline_sql_creates_new_schema_and_enforces_8014_rules():
    """离线生成不读取.env凭证，不建库，不输出旧结构或虚假的CHECK约束。"""
    output = StringIO()
    command.upgrade(config(output), "head", sql=True)
    sql = output.getvalue()
    assert "CREATE DATABASE" not in sql
    assert "CREATE TABLE study_records" not in sql
    assert "CREATE TABLE tags" not in sql
    assert "CHECK (" not in sql
    assert sql.count("CREATE TABLE ") == 33  # 32张业务表及Alembic版本表。
    assert sql.count("CREATE TRIGGER ") == 64
    assert all(rule != "1" for rule in baseline().TRIGGER_RULES.values())
    assert "expires_at" in baseline().TRIGGER_RULES["user_auth_sessions"]
    assert "source_stage_id" in baseline().TRIGGER_RULES["roadmap_stage_edges"]
    assert "completed_at" in baseline().TRIGGER_RULES["user_node_progress"]
    assert "roadmap_id IS NOT NULL" in baseline().TRIGGER_RULES["content_reports"]
    assert "issue_id IS NOT NULL" in baseline().TRIGGER_RULES["notifications"]
    assert REVISION in sql and "0004_roadmap_canvas" not in sql


@pytest.mark.parametrize(
    ("tables", "revisions"),
    [
        ({"users"}, []),
        ({"alembic_version", "users"}, ["0004_roadmap_canvas"]),
        ({"alembic_version"}, [REVISION]),
        ({"alembic_version", "unexpected"}, [REVISION]),
    ],
)
def test_preflight_rejects_legacy_partial_or_untracked_databases(tables, revisions):
    with pytest.raises(RuntimeError):
        baseline().validate_database_state(tables, revisions)


def test_preflight_accepts_only_empty_or_complete_new_database():
    migration = baseline()
    migration.validate_database_state(set(), [])
    migration.validate_database_state({"alembic_version"}, [])
    migration.validate_database_state(TABLES | {"alembic_version"}, [REVISION])


def test_new_initial_migration_never_drops_tables_on_downgrade():
    with pytest.raises(RuntimeError, match="不提供自动清库"):
        baseline().downgrade()


@pytest_asyncio.fixture
async def community_session():
    """仅连接显式测试库，核对结构后开启外层事务，测试结束全部回滚。"""
    from app.config.settings import Settings
    from app.database.crud.health import read_database_state
    from app.database.session import Database

    try:
        settings = Settings().for_community_tests()
    except ValueError as error:
        pytest.fail(str(error))
    database = Database(settings)
    try:
        async with database.engine.connect() as connection:
            transaction = await connection.begin()
            try:
                async with AsyncSession(
                    bind=connection, join_transaction_mode="create_savepoint"
                ) as session:
                    assert await session.scalar(text("SELECT DATABASE()")) == settings.db_name
                    state = await read_database_state(session)
                    assert state["version"].split("-")[0] == settings.db_required_version
                    assert state["revisions"] == [HEAD]
                    assert set(state["triggers"]) == EXPECTED_TRIGGERS
                    assert state["timezone"] == "+00:00" and state["fk_checks"] == 1
                    assert "STRICT_TRANS_TABLES" in state["sql_mode"]
                    yield session
            finally:
                await transaction.rollback()
    finally:
        await database.close()


@pytest_asyncio.fixture
async def community_rows(community_session):
    return await create_community_rows(community_session)


async def create_community_rows(community_session):
    """建立31表最小合法关系图，使用随机精确ID，不创建账号登录或演示数据。"""
    base = uuid4().int % 10**14 + 10**14
    now = datetime(2026, 11, 2, 0, 0, 0, 123456)
    key = str(uuid4())
    rows = {
        "users": dict(username="r01_" + uuid4().hex[:20], password_hash="test", nickname="测试"),
        "user_auth_sessions": dict(
            user_id=base, session_key=key, issued_at=now, expires_at=now + timedelta(hours=1)
        ),
        "user_privacy_settings": dict(user_id=base),
        "user_follows": dict(follower_id=base, followee_id=base + 1),
        "skill_roadmaps": dict(creator_id=base, title="约束测试路线"),
        "roadmap_stages": dict(
            roadmap_id=base,
            stable_key=key,
            title="阶段",
            position=1,
            canvas_x=Decimal("12.34"),
            canvas_y=Decimal("-56.78"),
        ),
        "learning_nodes": dict(
            roadmap_id=base, stage_id=base, stable_key=key, title="节点", position=1
        ),
        "node_resources": dict(
            node_id=base,
            title="资源",
            url="https://example.com",
            resource_type="article",
            position=1,
        ),
        "roadmap_stage_edges": dict(
            roadmap_id=base, source_stage_id=base, target_stage_id=base + 1
        ),
        "roadmap_releases": dict(
            roadmap_id=base,
            version_no=1,
            source_edit_version=1,
            title="版本",
            summary="简介",
            difficulty="beginner",
            license_code="UNSPECIFIED",
            update_summary="首版",
            content_hash="a" * 64,
            published_by=base,
            published_at=now,
        ),
        "release_stages": dict(
            release_id=base, stable_key=key, title="阶段", position=1, canvas_x=0, canvas_y=0
        ),
        "release_nodes": dict(
            release_id=base,
            stage_id=base,
            stable_key=key,
            title="节点",
            position=1,
            is_optional=0,
            counts_toward_progress=1,
            revision_no=1,
            change_policy="retain",
            canvas_x=0,
            canvas_y=0,
        ),
        "release_resources": dict(
            release_id=base,
            node_id=base,
            title="资源",
            url="https://example.com",
            resource_type="article",
            access_type="free",
            position=1,
        ),
        "release_stage_edges": dict(
            release_id=base, source_stage_id=base, target_stage_id=base + 1
        ),
        "roadmap_favorites": dict(user_id=base + 1, roadmap_id=base),
        "user_roadmaps": dict(user_id=base + 1, roadmap_id=base, started_at=now),
        "learning_sessions": dict(
            user_roadmap_id=base, roadmap_id=base, release_id=base, started_at=now
        ),
        "user_node_progress": dict(session_id=base, release_id=base, release_node_id=base),
        "learning_session_events": dict(
            user_roadmap_id=base,
            actor_id=base + 1,
            event_type="join",
            to_session_id=base,
            request_key=key,
        ),
        "roadmap_checkins": dict(
            user_roadmap_id=base, session_id=base, checkin_date=date(2026, 11, 2)
        ),
        "roadmap_issues": dict(
            roadmap_id=base, author_id=base + 1, title="问题", body="反馈", last_activity_at=now
        ),
        "issue_comments": dict(issue_id=base, author_id=base, body="回复"),
        "issue_subscriptions": dict(issue_id=base, user_id=base, subscription_source="author"),
        "issue_events": dict(issue_id=base, actor_id=base, event_type="created"),
        "roadmap_subscriptions": dict(roadmap_id=base, user_id=base + 1),
        "activity_events": dict(
            actor_id=base,
            activity_type="publish",
            roadmap_id=base,
            event_key=key,
            occurred_on=date(2026, 11, 2),
        ),
        "notification_outbox": dict(
            event_key=key, event_type="publish", payload={}, available_at=now
        ),
        "notifications": dict(
            recipient_id=base + 1,
            notification_type="reply",
            event_key=key,
            roadmap_id=base,
            issue_id=base,
            comment_id=base,
        ),
        "content_reports": dict(reporter_id=base + 1, roadmap_id=base, reason_code="spam"),
        "moderation_actions": dict(
            actor_id=base, target_type="roadmap", target_id=base, action="disable", reason="测试"
        ),
        "audit_logs": dict(
            actor_id=base,
            action_code="test",
            target_type="roadmap",
            request_id=key,
            result="success",
        ),
    }
    mapped = {mapper.local_table.name: mapper.class_ for mapper in Base.registry.mappers}

    async def add_row(name, values):
        """使用真实Mapped实例写入；外键依赖顺序由测试图显式给定。"""
        entity = mapped[name](**values)
        community_session.add(entity)
        await community_session.flush([entity])

    for name, values in rows.items():
        if name != "user_privacy_settings":
            values["id"] = base
        await add_row(name, values)
        if name == "users":
            await add_row(name, {**values, "id": base + 1, "username": "r01_" + uuid4().hex[:20]})
        elif name in {"roadmap_stages", "release_stages"}:
            await add_row(
                name, {**values, "id": base + 1, "stable_key": str(uuid4()), "position": 2}
            )
    return rows


@pytest.mark.database
@pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="需显式开启独立社区ORM测试")
@pytest.mark.parametrize("table_name", VALIDATED_TABLES)
async def test_all_community_models_round_trip_with_server_defaults(
    community_session, community_rows, table_name
):
    """31个实际映射均可写入再读取，非空列和服务端默认值在数据库中有效。"""
    model = next(m.class_ for m in Base.registry.mappers if m.local_table.name == table_name)
    key = next(iter(model.__table__.primary_key.columns))
    entity = await community_session.get(model, community_rows[table_name][key.name])
    assert type(entity) is model
    for column in model.__table__.c:
        if not column.nullable:
            assert getattr(entity, column.name) is not None
    for name, value in community_rows[table_name].items():
        assert getattr(entity, name) == value
    if "estimated_minutes" in model.__table__.c:
        assert entity.estimated_minutes is None


@pytest.mark.database
@pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="需显式开启独立社区ORM测试")
async def test_updated_at_requires_explicit_service_assignment(community_session, community_rows):
    """普通资料更新不偷偷改时间；服务层显式赋值后保留微秒精度。"""
    from app.database.models import User

    user = await community_session.get(User, community_rows["users"]["id"])
    before = user.updated_at
    user.bio = "验证时间写入边界"
    await community_session.flush()
    await community_session.refresh(user)
    assert user.updated_at == before
    supplied = datetime(2026, 11, 2, 1, 2, 3, 654321)
    user.updated_at = supplied
    await community_session.flush()
    await community_session.refresh(user)
    assert user.updated_at == supplied


INVALID_ROWS = {
    "users": {"role": "owner"},
    "user_auth_sessions": {"expires_at": datetime(2026, 11, 1)},
    "user_privacy_settings": {"settings_version": 0},
    "user_follows": {"followee_id": "self"},
    "skill_roadmaps": {"edit_version": 0},
    "roadmap_stages": {"position": 0},
    "learning_nodes": {"is_optional": 1, "counts_toward_progress": 1},
    "node_resources": {"resource_type": "unknown"},
    "roadmap_stage_edges": {"target_stage_id": "self"},
    "roadmap_releases": {"version_no": 0},
    "release_stages": {"position": 0},
    "release_nodes": {"estimated_minutes": 0},
    "release_resources": {"access_type": "invalid"},
    "release_stage_edges": {"target_stage_id": "self"},
    "roadmap_favorites": {"user_id": 0},
    "user_roadmaps": {"status": "unknown"},
    "learning_sessions": {"progress_version": 0},
    "user_node_progress": {"is_completed": 1, "completed_at": None},
    "learning_session_events": {"event_type": "upgrade", "from_session_id": None},
    "roadmap_checkins": {"is_valid": 2},
    "roadmap_issues": {"status": "unknown"},
    "issue_comments": {"visibility": "unknown"},
    "issue_subscriptions": {"subscription_source": "unknown"},
    "issue_events": {"event_type": "closed", "reason": "  "},
    "roadmap_subscriptions": {"is_subscribed": 2},
    "activity_events": {"visibility": "unknown"},
    "notification_outbox": {"status": "unknown"},
    "notifications": {"issue_id": None},
    "content_reports": {"roadmap_id": None},
    "moderation_actions": {"action": "unknown"},
    "audit_logs": {"result": "unknown"},
}


@pytest.mark.database
@pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="需显式开启独立社区约束测试")
@pytest.mark.parametrize("operation", ["insert", "update"])
@pytest.mark.parametrize("table_name", list(INVALID_ROWS))
async def test_community_triggers_reject_invalid_rows_and_preserve_transaction(
    community_session, community_rows, operation, table_name
):
    """逐个执行62个触发器，必须返回1644而非被外键或唯一键旁路拒绝。"""
    table = baseline().metadata.tables[table_name]
    values = community_rows[table_name]
    invalid = dict(INVALID_ROWS[table_name])
    if "self" in invalid.values():
        source = "follower_id" if table_name == "user_follows" else "source_stage_id"
        invalid = {
            name: values[source] if value == "self" else value for name, value in invalid.items()
        }
    key = next(iter(table.primary_key.columns))
    statement = (
        insert(table).values(**{**values, **invalid})
        if operation == "insert"
        else update(table).where(key == values[key.name]).values(**invalid)
    )
    with pytest.raises((IntegrityError, OperationalError)) as caught:
        async with community_session.begin_nested():
            await community_session.execute(statement)
    assert caught.value.orig.args[0] == 1644
    assert f"invalid_{table_name}" in str(caught.value.orig)
    assert (
        await community_session.scalar(select(key).where(key == values[key.name]))
        == values[key.name]
    )


@pytest.mark.database
@pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="需显式开启独立社区约束测试")
@pytest.mark.parametrize("table_name", ["user_roadmaps", "roadmap_checkins", "user_auth_sessions"])
async def test_community_business_uniqueness(community_session, community_rows, table_name):
    """重复关系、同日打卡及登录会话键由唯一键拒绝，不依赖服务端预查。"""
    table = baseline().metadata.tables[table_name]
    values = {**community_rows[table_name]}
    values["id"] += 100
    with pytest.raises(IntegrityError) as caught:
        async with community_session.begin_nested():
            await community_session.execute(insert(table).values(**values))
    assert caught.value.orig.args[0] == 1062
    assert await community_session.scalar(text("SELECT 1")) == 1


@pytest.mark.database
@pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="需显式开启独立社区约束测试")
@pytest.mark.parametrize(
    ("table_name", "field", "source_table"),
    [
        ("learning_nodes", "stage_id", "roadmap_stages"),
        ("release_nodes", "stage_id", "release_stages"),
        ("release_resources", "node_id", "release_nodes"),
        ("learning_sessions", "release_id", "roadmap_releases"),
        ("user_node_progress", "session_id", "learning_sessions"),
        ("user_node_progress", "release_node_id", "release_nodes"),
        ("user_roadmaps", "current_session_id", "learning_sessions"),
        ("skill_roadmaps", "current_release_id", "roadmap_releases"),
        ("roadmap_checkins", "session_id", "learning_sessions"),
        ("notifications", "comment_id", "issue_comments"),
        ("roadmap_stage_edges", "target_stage_id", "roadmap_stages"),
    ],
)
async def test_community_composite_foreign_keys_reject_cross_graph_links(
    community_session, community_rows, table_name, field, source_table
):
    """ID真实存在但归属不同的引用必须失败，覆盖串路线、串版和循环指针。"""
    other = await create_community_rows(community_session)
    table = baseline().metadata.tables[table_name]
    row_id = community_rows[table_name]["id"]
    changes = {field: other[source_table]["id"]}
    # 跨阶段/节点时避开既有位置唯一键，确保观察到的是归属外键。
    if table_name in {"release_nodes", "release_resources"}:
        changes["position"] = 10
    if table_name == "learning_sessions":
        # 原会话已被进度等记录引用，另插一条以排除父键RESTRICT的干扰。
        statement = insert(table).values(
            **{**community_rows[table_name], "id": row_id + 100, **changes}
        )
    else:
        statement = update(table).where(table.c.id == row_id).values(**changes)
    with pytest.raises(IntegrityError) as caught:
        async with community_session.begin_nested():
            await community_session.execute(statement)
    assert caught.value.orig.args[0] == 1452
    assert await community_session.scalar(text("SELECT 1")) == 1


@pytest.mark.database
@pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="需显式开启独立社区约束测试")
async def test_community_cycle_pointers_accept_matching_owner_and_reject_null(
    community_session, community_rows
):
    """合法循环指针可回填，必填昵称显式NULL被拒绝，事务继续可用。"""
    tables = baseline().metadata.tables
    base = community_rows["users"]["id"]
    for name, field in [
        ("skill_roadmaps", "current_release_id"),
        ("user_roadmaps", "current_session_id"),
    ]:
        table = tables[name]
        await community_session.execute(
            update(table).where(table.c.id == base).values(**{field: base})
        )
        assert (
            await community_session.scalar(select(table.c[field]).where(table.c.id == base)) == base
        )
    with pytest.raises(IntegrityError) as caught:
        async with community_session.begin_nested():
            await community_session.execute(
                update(tables["users"]).where(tables["users"].c.id == base).values(nickname=None)
            )
    assert caught.value.orig.args[0] == 1048
    assert await community_session.scalar(text("SELECT 1")) == 1


@pytest.mark.database
@pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="需显式开启独立社区测试库核验")
async def test_explicit_community_database_schema_is_complete():
    """只读核验显式测试目标；未配置或误指应用库时，在连接前失败。"""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from sqlalchemy import inspect, text

    from app.config.settings import Settings
    from app.database.crud.health import read_database_state
    from app.database.session import Database

    def compare_default(context, inspected, declared, actual, metadata_default, expected):
        """MySQL将DECIMAL零默认值规范化为0.00，按数值比较但仍检查真实变化。"""
        if isinstance(declared.type, Numeric) and actual is not None and expected is not None:
            return Decimal(actual.strip("'\"()")) != Decimal(expected.strip("'\"()"))
        return None

    try:
        settings = Settings().for_community_tests()
    except ValueError as error:
        pytest.fail(str(error))
    database = Database(settings)
    try:
        async with database.sessions() as session:
            assert await session.scalar(text("SELECT DATABASE()")) == settings.db_name
            state = await read_database_state(session)
            assert state["version"].split("-")[0] == settings.db_required_version
            assert state["timezone"] == "+00:00" and state["fk_checks"] == 1
            assert "STRICT_TRANS_TABLES" in state["sql_mode"]
            assert state["revisions"] == [HEAD]
            assert set(state["triggers"]) == EXPECTED_TRIGGERS
            connection = await session.connection()
            tables = await connection.run_sync(lambda conn: inspect(conn).get_table_names())
            assert set(tables) == TABLES | {"alembic_version", "resource_visits"}
            differences = await connection.run_sync(
                lambda conn: compare_metadata(
                    MigrationContext.configure(
                        conn,
                        opts={
                            "compare_type": True,
                            "compare_server_default": compare_default,
                        },
                    ),
                    Base.metadata,
                )
            )
            assert differences == []
            for name, table in Base.metadata.tables.items():
                columns = await connection.run_sync(
                    lambda conn, name=name: inspect(conn).get_columns(name)
                )
                assert [column["name"] for column in columns] == list(table.c.keys())
                for actual in columns:
                    declared = table.c[actual["name"]]
                    assert actual["nullable"] == declared.nullable
                    assert actual["comment"] == declared.comment
                    if isinstance(declared.type, Integer):
                        assert actual["type"].unsigned == declared.type.unsigned
                    if hasattr(declared.type, "fsp"):
                        assert actual["type"].fsp == declared.type.fsp == 6
                    if hasattr(declared.type, "length"):
                        assert actual["type"].length == declared.type.length
                    if getattr(declared.type, "charset", None) == "ascii":
                        assert actual["type"].collation == "ascii_bin"
            foreign_keys = (
                (
                    await session.execute(
                        text(
                            "SELECT REFERENCED_TABLE_SCHEMA "
                            "FROM information_schema.KEY_COLUMN_USAGE "
                            "WHERE TABLE_SCHEMA=DATABASE() AND REFERENCED_TABLE_NAME IS NOT NULL"
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert foreign_keys and set(foreign_keys) == {settings.db_name}
            rules = (
                await session.execute(
                    text(
                        "SELECT UPDATE_RULE, DELETE_RULE "
                        "FROM information_schema.REFERENTIAL_CONSTRAINTS "
                        "WHERE CONSTRAINT_SCHEMA=DATABASE()"
                    )
                )
            ).all()
            assert rules and all(tuple(row) == ("RESTRICT", "RESTRICT") for row in rules)
    finally:
        await database.close()
