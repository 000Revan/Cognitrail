"""真实 MySQL 约束验证：仅显式启用，所有测试数据均在事务结束时回滚。"""

import os
from datetime import date
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, insert, inspect, select, text, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings
from app.database.base import Base
from app.database.models import (
    LearningNode,
    NodeResource,
    ReleaseNode,
    ReleaseResource,
    ReleaseStage,
    RoadmapFavorite,
    RoadmapRelease,
    RoadmapStage,
    SkillRoadmap,
    StudyRecord,
    User,
    UserNodeProgress,
    UserRoadmap,
)
from app.database.session import Database
from app.database.validation import EXPECTED_TRIGGERS

pytestmark = [
    pytest.mark.skip(reason="旧十三表测试已隔离；社区约束测试按R01重新适配，不连接旧库"),
    pytest.mark.database,
    pytest.mark.skipif(
        os.getenv("RUN_DB_TESTS") != "1",
        reason="设置 RUN_DB_TESTS=1 才连接真实 MySQL",
    ),
]


@pytest_asyncio.fixture
async def session():
    pytest.skip("旧十三表夹具禁止连接数据库；新方向使用显式独立社区测试库")
    settings = Settings()
    if settings.db_name != "cognitrail" or settings.db_host not in {"127.0.0.1", "localhost"}:
        pytest.fail("S01 数据测试只允许本机 cognitrail 专用库")
    database = Database(settings)
    try:
        async with database.engine.connect() as connection:
            transaction = await connection.begin()
            assert (await connection.execute(text("SELECT VERSION()"))).scalar_one() == "8.0.14"
            async with AsyncSession(bind=connection, join_transaction_mode="create_savepoint") as s:
                yield s
            await transaction.rollback()
    finally:
        await database.close()


@pytest_asyncio.fixture
async def data(session):
    """创建随机隔离记录；仅作为数据库夹具，不代表业务功能已实现。"""
    base = uuid4().int % 10**14 + 10**14
    user, roadmap, stage, node, enrollment = [base + i for i in range(5)]
    await session.execute(
        insert(User).values(id=user, username=f"test_{base}", password_hash="test")
    )
    await session.execute(
        insert(SkillRoadmap).values(
            id=roadmap,
            creator_id=user,
            roadmap_type="user",
            title="测试路线",
        )
    )
    await session.execute(
        insert(RoadmapStage).values(id=stage, roadmap_id=roadmap, title="测试阶段")
    )
    await session.execute(
        insert(LearningNode).values(
            id=node,
            stage_id=stage,
            title="测试节点",
            learning_objective="目标",
        )
    )
    await session.execute(
        insert(NodeResource).values(
            node_id=node,
            title="资源",
            resource_url="https://example.com",
        )
    )
    await session.execute(
        insert(RoadmapRelease).values(
            id=roadmap,
            roadmap_id=roadmap,
            version_no=1,
            source_edit_version=0,
            title="冻结路线V1",
            difficulty="beginner",
        )
    )
    await session.execute(
        insert(ReleaseStage).values(id=stage, release_id=roadmap, position=1, title="冻结阶段")
    )
    await session.execute(
        insert(ReleaseNode).values(
            id=node,
            release_id=roadmap,
            stage_id=stage,
            position=1,
            title="冻结节点",
            learning_objective="目标",
            estimated_minutes=60,
        )
    )
    await session.execute(
        insert(ReleaseResource).values(
            release_id=roadmap,
            node_id=node,
            position=1,
            title="冻结资源",
            resource_type="article",
            resource_url="https://example.com/v1",
        )
    )
    await session.execute(
        insert(UserRoadmap).values(
            id=enrollment, user_id=user, roadmap_id=roadmap, release_id=roadmap
        )
    )
    return {
        "user": user,
        "roadmap": roadmap,
        "stage": stage,
        "node": node,
        "enrollment": enrollment,
        "release": roadmap,
    }


async def test_schema_and_session(session):
    connection = await session.connection()
    tables = await connection.run_sync(lambda c: inspect(c).get_table_names())
    assert set(tables) == set(Base.metadata.tables) | {"alembic_version"}
    config = (
        await session.execute(text("SELECT @@time_zone, @@foreign_key_checks, @@sql_mode"))
    ).one()
    assert config[0] == "+00:00" and config[1] == 1 and "STRICT_TRANS_TABLES" in config[2]
    triggers = (
        (
            await session.execute(
                text(
                    "SELECT TRIGGER_NAME FROM information_schema.TRIGGERS "
                    "WHERE TRIGGER_SCHEMA=DATABASE()"
                )
            )
        )
        .scalars()
        .all()
    )
    assert set(triggers) == EXPECTED_TRIGGERS
    for table in Base.metadata.sorted_tables:
        columns = await connection.run_sync(lambda c, name=table.name: inspect(c).get_columns(name))
        assert {c["name"] for c in columns} == {c.name for c in table.columns}
        checks = await connection.run_sync(
            lambda c, name=table.name: inspect(c).get_check_constraints(name)
        )
        expected_checks = [
            x for x in table.constraints if x.__class__.__name__ == "CheckConstraint"
        ]
        assert len(checks) == len(expected_checks)


RULE_CASES = [
    ("users", "role", "owner"),
    ("users", "is_active", 2),
    ("users", "auth_version", -1),
    ("skill_roadmaps", "roadmap_type", "unknown"),
    ("skill_roadmaps", "difficulty", "expert"),
    ("skill_roadmaps", "status", "unknown"),
    ("skill_roadmaps", "edit_version", -1),
    ("learning_nodes", "estimated_minutes", 0),
    ("node_resources", "resource_type", "unknown"),
    ("user_roadmaps", "status", "unknown"),
    ("user_node_progress", "status", "locked"),
    ("study_records", "duration_minutes", -1),
    ("roadmap_releases", "version_no", 0),
    ("roadmap_releases", "source_edit_version", -1),
    ("roadmap_releases", "difficulty", "expert"),
    ("release_stages", "position", 0),
    ("release_nodes", "position", 0),
    ("release_nodes", "estimated_minutes", 0),
    ("release_resources", "position", 0),
    ("release_resources", "resource_type", "unknown"),
]


@pytest.mark.parametrize("operation", ["insert", "update"])
@pytest.mark.parametrize(("table_name", "field", "invalid"), RULE_CASES)
async def test_every_validation_rule_protects_insert_and_update(
    session,
    data,
    operation,
    table_name,
    field,
    invalid,
):
    """逐项验证全部二十条规则的 INSERT/UPDATE 保护，不依赖 ORM 校验。"""
    valid_values = {
        "users": {"username": f"test_{uuid4().hex}", "password_hash": "test"},
        "skill_roadmaps": {"creator_id": data["user"], "roadmap_type": "user", "title": "测试"},
        "learning_nodes": {
            "stage_id": data["stage"],
            "title": "测试",
            "learning_objective": "目标",
        },
        "node_resources": {
            "node_id": data["node"],
            "title": "测试",
            "resource_url": "https://example.com",
        },
        "user_roadmaps": {
            "user_id": data["user"],
            "roadmap_id": data["roadmap"],
            "release_id": data["release"],
        },
        "user_node_progress": {
            "user_roadmap_id": data["enrollment"],
            "release_node_id": data["node"],
            "release_id": data["release"],
        },
        "study_records": {
            "user_roadmap_id": data["enrollment"],
            "request_key": str(uuid4()),
            "study_date": date.today(),
        },
        "roadmap_releases": {
            "roadmap_id": data["roadmap"],
            "version_no": 2,
            "source_edit_version": 1,
            "title": "新版",
            "difficulty": "beginner",
        },
        "release_stages": {"release_id": data["release"], "position": 2, "title": "阶段"},
        "release_nodes": {
            "release_id": data["release"],
            "stage_id": data["stage"],
            "position": 2,
            "title": "节点",
            "learning_objective": "目标",
            "estimated_minutes": 60,
        },
        "release_resources": {
            "release_id": data["release"],
            "node_id": data["node"],
            "position": 2,
            "title": "资源",
            "resource_type": "article",
            "resource_url": "https://example.com",
        },
    }
    table = Base.metadata.tables[table_name]
    values = valid_values[table_name]
    if operation == "update":
        # 学习关系已由夹具创建，不违反唯一约束创建第二条关系。
        if table_name == "user_roadmaps":
            row_id = data["enrollment"]
        else:
            result = await session.execute(insert(table).values(**values))
            row_id = result.inserted_primary_key[0]
        statement = update(table).where(table.c.id == row_id).values(**{field: invalid})
    else:
        statement = insert(table).values(**{**values, field: invalid})
    with pytest.raises((IntegrityError, OperationalError)) as error:
        async with session.begin_nested():
            await session.execute(statement)
    # SQLSTATE 45000 对应 MySQL 1644，确保确实由触发器拒绝，而非唯一键等旁路错误。
    assert error.value.orig.args[0] == 1644


@pytest.mark.parametrize("minutes", [0, -1])
async def test_nonpositive_minutes_rejected(session, data, minutes):
    with pytest.raises((IntegrityError, OperationalError)):
        async with session.begin_nested():
            await session.execute(
                insert(StudyRecord).values(
                    user_roadmap_id=data["enrollment"],
                    duration_minutes=minutes,
                    request_key=str(uuid4()),
                    study_date=date.today(),
                )
            )


async def test_null_minutes_multiple_progress_and_idempotency_constraint(session, data):
    second = data["node"] + 100
    await session.execute(
        insert(ReleaseNode).values(
            id=second,
            stage_id=data["stage"],
            release_id=data["release"],
            position=2,
            estimated_minutes=60,
            title="另一节点",
            learning_objective="目标",
        )
    )
    for node in [data["node"], second]:
        await session.execute(
            insert(UserNodeProgress).values(
                user_roadmap_id=data["enrollment"],
                release_node_id=node,
                release_id=data["release"],
                status="in_progress",
            )
        )
    key = str(uuid4())
    values = dict(
        user_roadmap_id=data["enrollment"],
        request_key=key,
        study_date=date.today(),
    )
    await session.execute(insert(StudyRecord).values(**values))
    record = (await session.execute(select(StudyRecord))).scalars().all()
    assert any(r.request_key == key and r.duration_minutes is None for r in record)
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            await session.execute(insert(StudyRecord).values(**values))


@pytest.mark.parametrize("delete_stage", [False, True])
async def test_route_checkins_and_personal_notes_survive_content_deletion(
    session, data, delete_stage
):
    """删工作稿节点或阶段均不影响冻结目录、个人进度和路线打卡。"""
    await session.execute(
        insert(UserNodeProgress).values(
            user_roadmap_id=data["enrollment"],
            release_node_id=data["node"],
            release_id=data["release"],
            notes="保留这份个人总结",
        )
    )
    for minutes in [None, 25]:
        await session.execute(
            insert(StudyRecord).values(
                user_roadmap_id=data["enrollment"],
                duration_minutes=minutes,
                content=None if minutes is None else "路线整体收获",
                request_key=str(uuid4()),
                study_date=date(2026, 10, 30),
            )
        )
    query = (
        select(StudyRecord.__table__)
        .where(StudyRecord.user_roadmap_id == data["enrollment"])
        .order_by(StudyRecord.id)
    )
    before = (await session.execute(query)).mappings().all()
    if delete_stage:
        await session.execute(delete(RoadmapStage).where(RoadmapStage.id == data["stage"]))
    else:
        await session.execute(delete(LearningNode).where(LearningNode.id == data["node"]))
    assert (await session.execute(query)).mappings().all() == before
    history = (
        await session.execute(
            select(UserNodeProgress.release_node_id, UserNodeProgress.notes).where(
                UserNodeProgress.user_roadmap_id == data["enrollment"]
            )
        )
    ).one()
    assert history == (data["node"], "保留这份个人总结")
    assert (
        await session.execute(select(ReleaseNode.title).where(ReleaseNode.id == data["node"]))
    ).scalar_one() == "冻结节点"
    # 内容删除后仍可纯打卡，且时长只累加已填写记录。
    await session.execute(
        insert(StudyRecord).values(
            user_roadmap_id=data["enrollment"],
            request_key=str(uuid4()),
            study_date=date(2026, 10, 30),
        )
    )
    totals = (
        await session.execute(
            select(func.count(), func.sum(StudyRecord.duration_minutes)).where(
                StudyRecord.user_roadmap_id == data["enrollment"]
            )
        )
    ).one()
    assert totals == (3, 25)
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            await session.execute(delete(UserRoadmap).where(UserRoadmap.id == data["enrollment"]))


async def test_checkin_still_requires_an_existing_route_relationship(session):
    """解除节点依赖不代表可以产生没有用户路线归属的记录。"""
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            await session.execute(
                insert(StudyRecord).values(
                    user_roadmap_id=-1,
                    request_key=str(uuid4()),
                    study_date=date.today(),
                )
            )


async def test_parent_foreign_key_invalid_status_and_unique_relationships(session, data):
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            await session.execute(insert(RoadmapStage).values(roadmap_id=-1, title="无效父级"))
    with pytest.raises((IntegrityError, OperationalError)):
        async with session.begin_nested():
            await session.execute(
                insert(UserNodeProgress).values(
                    user_roadmap_id=data["enrollment"],
                    release_node_id=data["node"],
                    release_id=data["release"],
                    status="locked",
                )
            )
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            await session.execute(
                insert(UserRoadmap).values(
                    user_id=data["user"],
                    roadmap_id=data["roadmap"],
                    release_id=data["release"],
                )
            )
    await session.execute(
        insert(RoadmapFavorite).values(
            user_id=data["user"],
            roadmap_id=data["roadmap"],
        )
    )
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            await session.execute(
                insert(RoadmapFavorite).values(
                    user_id=data["user"],
                    roadmap_id=data["roadmap"],
                )
            )


async def test_new_release_enrollment_archiving_and_moderation_preserve_history(session, data):
    """跨版本独立报名、收藏不消失、下架与归档不抹除历史统计。"""
    second_release = data["release"] + 100
    await session.execute(
        insert(RoadmapRelease).values(
            id=second_release,
            roadmap_id=data["roadmap"],
            version_no=2,
            source_edit_version=1,
            title="新版V2",
            difficulty="advanced",
        )
    )
    await session.execute(
        insert(UserRoadmap).values(
            user_id=data["user"],
            roadmap_id=data["roadmap"],
            release_id=second_release,
        )
    )
    await session.execute(
        insert(RoadmapFavorite).values(
            user_id=data["user"],
            roadmap_id=data["roadmap"],
        )
    )
    await session.execute(
        insert(StudyRecord).values(
            user_roadmap_id=data["enrollment"],
            duration_minutes=25,
            request_key=str(uuid4()),
            study_date=date(2026, 10, 30),
        )
    )
    await session.execute(
        update(SkillRoadmap)
        .where(SkillRoadmap.id == data["roadmap"])
        .values(
            current_release_id=second_release,
            status="published",
            title="工作稿改名",
        )
    )
    query = select(func.count(), func.sum(StudyRecord.duration_minutes)).where(
        StudyRecord.user_roadmap_id == data["enrollment"]
    )
    before = (await session.execute(query)).one()
    for state in ["withdrawn", "disabled"]:
        await session.execute(
            update(SkillRoadmap).where(SkillRoadmap.id == data["roadmap"]).values(status=state)
        )
        assert (await session.execute(query)).one() == before == (1, 25)
    await session.execute(
        update(UserRoadmap)
        .where(UserRoadmap.id == data["enrollment"])
        .values(archived_at=text("UTC_TIMESTAMP(6)"))
    )
    assert (await session.execute(query)).one() == before
    assert (
        await session.execute(
            select(func.count()).select_from(UserRoadmap).where(UserRoadmap.user_id == data["user"])
        )
    ).scalar_one() == 2
    assert (
        await session.execute(
            select(func.count())
            .select_from(RoadmapFavorite)
            .where(RoadmapFavorite.roadmap_id == data["roadmap"])
        )
    ).scalar_one() == 1
    assert (
        await session.execute(
            select(RoadmapRelease.title).where(RoadmapRelease.id == data["release"])
        )
    ).scalar_one() == "冻结路线V1"
    # 即使绕过服务层，数据库也拒绝将旧学习关系的进度写到新版节点。
    stage2 = (
        await session.execute(
            insert(ReleaseStage).values(release_id=second_release, position=1, title="新版阶段")
        )
    ).inserted_primary_key[0]
    node2 = (
        await session.execute(
            insert(ReleaseNode).values(
                release_id=second_release,
                stage_id=stage2,
                position=1,
                title="新版节点",
                learning_objective="目标",
                estimated_minutes=60,
            )
        )
    ).inserted_primary_key[0]
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            await session.execute(
                insert(UserNodeProgress).values(
                    user_roadmap_id=data["enrollment"],
                    release_id=data["release"],
                    release_node_id=node2,
                )
            )


async def test_release_route_and_parent_consistency_are_database_enforced(session, data):
    """拒绝跨路线当前版本指针及跨版本阶段、节点混接。"""
    other_route = (
        await session.execute(
            insert(SkillRoadmap).values(
                creator_id=data["user"],
                roadmap_type="user",
                title="另一条路线",
            )
        )
    ).inserted_primary_key[0]
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            await session.execute(
                update(SkillRoadmap)
                .where(SkillRoadmap.id == other_route)
                .values(current_release_id=data["release"])
            )
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            await session.execute(
                insert(UserRoadmap).values(
                    user_id=data["user"], roadmap_id=other_route, release_id=data["release"]
                )
            )
    other_release = (
        await session.execute(
            insert(RoadmapRelease).values(
                roadmap_id=other_route,
                version_no=1,
                source_edit_version=0,
                title="其他发布版",
                difficulty="beginner",
            )
        )
    ).inserted_primary_key[0]
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            await session.execute(
                insert(ReleaseNode).values(
                    release_id=other_release,
                    stage_id=data["stage"],
                    position=2,
                    title="混接节点",
                    learning_objective="目标",
                    estimated_minutes=60,
                )
            )
