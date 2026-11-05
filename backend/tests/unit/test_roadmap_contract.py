"""社区工作稿及冻结版本的结构契约，不代表发布服务已开放。"""

from app.database import models  # noqa: F401
from app.database.base import Base


def test_author_archiving_and_edges_are_separate_from_learning_sessions():
    assert "author_archived_at" in Base.metadata.tables["skill_roadmaps"].c
    for table in ("skill_roadmaps", "roadmap_releases"):
        assert "connections" not in Base.metadata.tables[table].c
    assert "roadmap_stage_edges" in Base.metadata.tables
    assert "release_stage_edges" in Base.metadata.tables


def test_canvas_and_optional_content_survive_publication():
    for table in ("roadmap_stages", "learning_nodes", "release_stages", "release_nodes"):
        assert {"canvas_x", "canvas_y"} <= set(Base.metadata.tables[table].c.keys())
    for table in ("learning_nodes", "release_nodes"):
        assert Base.metadata.tables[table].c.estimated_minutes.nullable
        assert "tips" in Base.metadata.tables[table].c


def test_learning_writes_require_session_and_reject_legacy_fields():
    import pytest
    from pydantic import ValidationError

    from app.schemas.enrollment import NodeStatusUpdate, PositionUpdate, StudyRecordCreate

    assert NodeStatusUpdate(sessionId="1", completed=True).completed is True
    assert PositionUpdate(sessionId="1", nodeId="2").node_id == 2
    assert StudyRecordCreate(sessionId="1").session_id == 1
    for payload in (
        {},
        {"sessionId": "1", "content": "旧收获"},
        {"sessionId": "1", "studyDate": "2026-11-01"},
    ):
        with pytest.raises(ValidationError):
            StudyRecordCreate(**payload)


def test_checkin_day_statistics_deduplicate_routes_and_keep_yesterday_streak():
    from datetime import date

    from app.services.enrollment_service import day_statistics

    days = [date(2026, 10, 30), date(2026, 10, 31), date(2026, 10, 31)]
    assert day_statistics(days, date(2026, 11, 1)) == (2, 2, 2)
    assert day_statistics(days, date(2026, 11, 2)) == (2, 0, 2)


def test_retired_learning_writes_are_absent_from_openapi():
    from app.config.settings import Settings
    from app.main import create_app

    paths = create_app(Settings(_env_file=None)).openapi()["paths"]
    assert "/api/v1/users/me/study-records" not in paths
    for path, methods in paths.items():
        assert not path.endswith("/notes")
        assert not path.endswith("/history")
        assert not path.startswith("/api/v1/study-records/")
        if path.endswith("/records"):
            assert "patch" not in methods and "delete" not in methods


def test_upgrade_requires_bound_source_version_and_unique_explicit_choices():
    from uuid import uuid4

    import pytest
    from pydantic import ValidationError

    from app.schemas.enrollment import UpgradeRequest

    payload = dict(
        sourceSessionId="1",
        targetReleaseId="2",
        progressVersion=3,
        requestKey=str(uuid4()),
        confirmations=[],
    )
    assert UpgradeRequest(**payload).progress_version == 3
    for patch in (
        {"progressVersion": True},
        {"sourceSessionId": "0"},
        {"requestKey": "bad"},
        {"confirmations": [{"stableKey": str(uuid4()), "action": "maybe"}]},
    ):
        with pytest.raises(ValidationError):
            UpgradeRequest(**{**payload, **patch})
    choice = {"stableKey": str(uuid4()), "action": "keep"}
    with pytest.raises(ValidationError):
        UpgradeRequest(**{**payload, "confirmations": [choice, choice]})


def test_upgrade_plan_uses_semantic_revision_and_current_source_only():
    from app.domain.roadmap_policy import learning_upgrade_plan

    def node(key, revision=1, **values):
        return dict(
            id=key,
            stableKey=key,
            revisionNo=revision,
            title=key,
            stageKey="s",
            stageTitle="阶段",
            position=1,
            content="正文",
            tips=None,
            estimatedMinutes=None,
            isOptional=False,
            countsTowardProgress=True,
            resources=[],
            canvasX=0,
            canvasY=0,
            **values,
        )

    source = [node("keep"), node("semantic"), node("removed")]
    target = [node("keep"), node("semantic", 2), node("restored")]
    plan = learning_upgrade_plan(source, target, {"keep", "semantic", "removed"}, "removed", {})
    assert plan["requiredKeys"] == {"semantic"}
    assert plan["completedMin"] == 1 and plan["completedMax"] == 2
    # restored不存在于当前源版本，不能从更早历史找回完成。
    assert "restored" not in plan["completedKeys"]
    assert plan["lastNodeKey"] == "semantic"
    kept = learning_upgrade_plan(
        source, target, {"keep", "semantic", "removed"}, "removed", {"semantic": "keep"}
    )
    assert kept["completedKeys"] == {"keep", "semantic"}
    assert kept["lastNodeKey"] == "restored"


def test_move_and_optional_progress_changes_do_not_reset_same_semantics():
    from app.domain.roadmap_policy import learning_upgrade_plan

    first = dict(
        id=1,
        stableKey="a",
        revisionNo=1,
        title="旧名",
        stageKey="old",
        stageTitle="原阶段",
        position=1,
        content="目标",
        tips=None,
        estimatedMinutes=None,
        isOptional=False,
        countsTowardProgress=True,
        resources=[],
        canvasX=0,
        canvasY=0,
    )
    second = {**first, "id": 2, "stableKey": "b"}
    moved = {
        **first,
        "id": 3,
        "stageKey": "new",
        "stageTitle": "新阶段",
        "position": 2,
        "title": "新名",
        "isOptional": True,
        "countsTowardProgress": False,
        "resources": [("新资源",)],
    }
    plan = learning_upgrade_plan([first, second], [second, moved], {"a"}, "a", {})
    assert plan["completedKeys"] == {"a"} and not plan["requiredKeys"]
    assert plan["targetTotal"] == 1 and plan["completedCount"] == 0
    assert plan["lastNodeKey"] == "a"
    assert {"moved", "renamed", "optional", "progress", "resources"} <= set(
        plan["nodeChanges"][0]["changes"]
    )
