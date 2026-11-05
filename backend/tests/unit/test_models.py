"""静态检查数据模型与冻结迁移，不替代真实 MySQL 约束测试。"""

from types import SimpleNamespace

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import MetaData, inspect
from sqlalchemy.dialects.mysql import dialect
from sqlalchemy.orm import configure_mappers
from sqlalchemy.schema import CreateTable

from app.config.settings import BACKEND_ROOT
from app.database import models
from app.database.base import Base
from app.database.validation import VALIDATED_TABLES


@pytest.fixture(scope="module")
def frozen_metadata():
    """读取独立冻结基线，不以当前ORM自行证明正确。"""
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    scripts = ScriptDirectory.from_config(config)
    original = scripts.get_revision("c001_community").module.metadata
    frozen = SimpleNamespace(tables=dict(original.tables))
    # 仅复制增量涉及的表，保持其他冻结表的约束声明顺序。
    notification = original.tables["notifications"].to_metadata(MetaData())
    notification.append_column(
        scripts.get_revision("c002_notification_delete").module.deleted_at_column()
    )
    frozen.tables["notifications"] = notification
    roadmap = original.tables["skill_roadmaps"].to_metadata(MetaData())
    roadmap.append_column(
        scripts.get_revision("c003_official_roadmaps").module.roadmap_type_column()
    )
    frozen.tables["skill_roadmaps"] = roadmap
    privacy = original.tables["user_privacy_settings"].to_metadata(MetaData())
    privacy.append_column(scripts.get_revision("c004_topic_privacy").module.topic_public_column())
    frozen.tables["user_privacy_settings"] = privacy
    return frozen


def table_signature(table):
    """比较列顺序/精度/空值/默认/注释及命名约束，覆盖自动迁移易漏细节。"""
    return {
        "ddl": str(CreateTable(table).compile(dialect=dialect())),
        "columns": [
            (
                c.name,
                str(c.type.compile(dialect=dialect())),
                c.nullable,
                c.primary_key,
                c.autoincrement,
                str(c.server_default.arg) if c.server_default else None,
                c.comment,
                c.onupdate,
                c.server_onupdate,
            )
            for c in table.c
        ],
        "foreign_keys": sorted(
            (
                fk.name,
                tuple(e.parent.name for e in fk.elements),
                tuple(e.target_fullname for e in fk.elements),
                fk.ondelete,
                fk.onupdate,
                fk.use_alter,
            )
            for fk in table.foreign_key_constraints
        ),
        "uniques": sorted(
            (key.name, tuple(c.name for c in key.columns))
            for key in table.constraints
            if key.__class__.__name__ == "UniqueConstraint"
        ),
        "indexes": sorted(
            (index.name, tuple(c.name for c in index.columns), index.unique)
            for index in table.indexes
        ),
        "options": dict(table.dialect_kwargs),
    }


def test_all_models_use_one_base_and_export_actual_mapped_classes(frozen_metadata):
    configure_mappers()
    assert set(Base.metadata.tables) == set(VALIDATED_TABLES) | {"resource_visits"}
    assert Base.metadata is not frozen_metadata
    mapped = {mapper.local_table.name: mapper.class_ for mapper in Base.registry.mappers}
    assert set(mapped) == set(VALIDATED_TABLES) | {"resource_visits"}
    assert len(mapped) == len(models.__all__) == 32
    assert all(inspect(getattr(models, name)).registry is Base.registry for name in models.__all__)


@pytest.mark.parametrize("name", VALIDATED_TABLES)
def test_orm_matches_independent_frozen_schema(name, frozen_metadata):
    assert table_signature(Base.metadata.tables[name]) == table_signature(
        frozen_metadata.tables[name]
    )
    assert Base.metadata.tables[name] is not frozen_metadata.tables[name]


def test_retired_study_record_is_not_mapped_or_aliased_to_daily_checkin():
    assert "study_records" not in Base.metadata.tables
    assert inspect(models.StudyRecord, raiseerr=False) is None
    assert models.StudyRecord is not models.RoadmapCheckin
    with pytest.raises(RuntimeError, match="已退役"):
        models.StudyRecord(user_roadmap_id=1)


def test_checkins_belong_to_routes_and_never_require_a_node():
    """阶段、节点只是路线内容，路线打卡不能依赖它们存在。"""
    records = Base.metadata.tables["roadmap_checkins"]
    assert not {"node_id", "content", "duration_minutes"} & set(records.c.keys())
    assert "session_id" in records.c
    assert not records.c.user_roadmap_id.nullable


def test_progress_binds_to_release_nodes_instead_of_mutable_draft_nodes():
    """个人节点历史必须绑定冻结版本，作者删除工作稿节点不能影响学习。"""
    progress = Base.metadata.tables["user_node_progress"]
    assert "node_id" not in progress.c
    assert not progress.c.release_node_id.nullable
    assert {fk.target_fullname for fk in progress.c.release_node_id.foreign_keys} == {
        "release_nodes.id"
    }


def test_enrollment_is_unique_per_user_and_roadmap_with_separate_sessions():
    """同路线只有一个关系，各版本进度由学习会话承载。"""
    table = Base.metadata.tables["user_roadmaps"]
    uniques = {
        tuple(c.name for c in x.columns)
        for x in table.constraints
        if x.__class__.__name__ == "UniqueConstraint"
    }
    assert ("user_id", "roadmap_id") in uniques
    assert "release_id" not in table.c
    assert table.c.current_session_id.nullable
    assert "release_id" in Base.metadata.tables["learning_sessions"].c
    assert "session_key" in Base.metadata.tables["user_auth_sessions"].c


def test_release_content_has_no_foreign_keys_to_mutable_content():
    """冻结内容保存独立结构，工作稿节点删除不能级联到发布版本。"""
    for name in ["release_stages", "release_nodes", "release_resources"]:
        table = Base.metadata.tables[name]
        assert "position" in table.c
        assert not any(
            fk.column.table.name in {"roadmap_stages", "learning_nodes", "node_resources"}
            for fk in table.foreign_keys
        )
    roadmap = Base.metadata.tables["skill_roadmaps"]
    assert "current_release_id" in roadmap.c
    assert "moderation_status" in roadmap.c
