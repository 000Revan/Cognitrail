"""检查断库、迁移版本、异常脱敏及真实健康响应契约。"""

from datetime import UTC, datetime
from typing import Annotated
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Body
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from app.config.settings import Settings
from app.database.validation import EXPECTED_TRIGGERS
from app.main import create_app
from app.schemas.common import JsonId, PageParams, Schema, UtcDateTime
from app.services.health_service import HealthService, migration_heads


def settings() -> Settings:
    return Settings(
        _env_file=None, db_password="test-only-not-a-real-password", outbox_enabled=False
    )


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/api/v1/roadmaps/1/withdraw"),
    ],
)
def test_pending_community_endpoints_never_acquire_database_session(method, path):
    """业务开放先于身份及数据库依赖检查，防止旧SQL写入新库。"""
    from app.database.session import get_session

    app = create_app(settings())

    async def forbidden_session():
        pytest.fail("未适配接口不得获取数据库会话")
        yield

    app.dependency_overrides[get_session] = forbidden_session
    with TestClient(app) as client:
        response = client.request(method, path, json={})
    assert response.status_code == 503
    assert response.json()["data"]["errorCode"] == "COMMUNITY_FEATURE_NOT_READY"
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["data"]["requestId"] == response.headers["x-request-id"]


@pytest.mark.parametrize("name", [None, "cognitrail", "cognitrail_community", "other_test"])
def test_community_tests_reject_missing_or_unsafe_database_target(name):
    """测试目标必须显式独立，不能沿用开发库或保留的旧库。"""
    with pytest.raises(ValueError):
        Settings(_env_file=None, test_db_name=name).for_community_tests()


def test_community_tests_use_explicit_target_without_changing_application_settings():
    config = Settings(
        _env_file=None,
        db_name="cognitrail_community",
        test_db_name="cognitrail_community_test_r01",
    )
    isolated = config.for_community_tests()
    assert isolated.db_name == "cognitrail_community_test_r01"
    assert config.db_name == "cognitrail_community"
    assert isolated.database_url.database != config.database_url.database


async def test_legacy_admin_bootstrap_is_blocked_before_connecting_or_prompting(monkeypatch):
    """维护脚本也遵循开放边界，不能在R01写入不完整的新账号。"""
    from unittest.mock import Mock

    from app.core.exceptions import AppError
    from app.schemas.auth import RegisterRequest
    from scripts import create_admin

    monkeypatch.setattr(create_admin.validation, "COMMUNITY_ENABLED_ENDPOINTS", frozenset())

    database = Mock(side_effect=AssertionError("不得创建数据库连接"))
    prompt = Mock(side_effect=AssertionError("未开放时不收集密码"))
    monkeypatch.setattr(create_admin, "Database", database)
    monkeypatch.setattr(create_admin, "getpass", prompt)
    data = RegisterRequest(username="r01_admin", password="abcdef", nickname="测试")
    with pytest.raises(AppError) as caught:
        await create_admin.create(data)
    assert caught.value.error_code == "COMMUNITY_FEATURE_NOT_READY"
    monkeypatch.setattr("sys.argv", ["create_admin", "--username", "r01_admin"])
    with pytest.raises(SystemExit, match="暂未开放"):
        create_admin.main()
    database.assert_not_called()
    prompt.assert_not_called()


def test_live_does_not_access_database():
    """进程存活检查在数据库完全不可用时仍返回 200。"""
    with TestClient(create_app(settings())) as client:
        with patch("app.database.crud.health.AsyncSession.execute", side_effect=AssertionError):
            response = client.get("/health/live")
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "alive"
        assert response.json()["data"]["checkedAt"].endswith("Z")
        assert response.headers["x-request-id"]


def test_database_error_is_503_and_does_not_leak_connection():
    with patch("app.services.health_service.read_database_state", new_callable=AsyncMock) as read:
        read.side_effect = OperationalError("SECRET_SQL", {}, Exception("PASSWORD_SHOULD_NOT_LEAK"))
        with TestClient(create_app(settings())) as client:
            response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["data"]["errorCode"] == "DATABASE_NOT_READY"
        assert response.json()["data"]["requestId"] == response.headers["x-request-id"]
        assert "PASSWORD_SHOULD_NOT_LEAK" not in response.text
        assert "SECRET_SQL" not in response.text


@pytest.mark.parametrize(
    ("overrides", "expected_code"),
    [
        ({"version": "8.0.13"}, "DATABASE_VERSION_MISMATCH"),
        ({"revisions": []}, "MIGRATION_REQUIRED"),
        ({"revisions": ["old_revision"]}, "MIGRATION_REQUIRED"),
        ({"revisions": ["0001_initial"]}, "MIGRATION_REQUIRED"),
        ({"timezone": "+08:00"}, "DATABASE_CONFIGURATION_MISMATCH"),
        ({"fk_checks": 0}, "DATABASE_CONFIGURATION_MISMATCH"),
        ({"sql_mode": ""}, "DATABASE_CONFIGURATION_MISMATCH"),
        ({"triggers": []}, "DATABASE_VALIDATION_MISSING"),
    ],
)
async def test_ready_rejects_incompatible_environment(overrides, expected_code):
    state = {
        "version": "8.0.14",
        "revisions": list(migration_heads()),
        "timezone": "+00:00",
        "sql_mode": "STRICT_TRANS_TABLES",
        "fk_checks": 1,
        "triggers": list(EXPECTED_TRIGGERS),
        **overrides,
    }
    from app.core.exceptions import AppError

    with patch("app.services.health_service.read_database_state", new_callable=AsyncMock) as read:
        read.return_value = state
        with pytest.raises(AppError) as error:
            await HealthService(settings()).ready(AsyncMock())
    assert error.value.error_code == expected_code


async def test_ready_returns_camel_case_when_database_and_migration_match():
    with (
        patch("app.services.health_service.COMMUNITY_APPLICATION_READY", True),
        patch("app.services.health_service.read_database_state", new_callable=AsyncMock) as read,
    ):
        read.return_value = {
            "version": "8.0.14",
            "revisions": list(migration_heads()),
            "timezone": "+00:00",
            "sql_mode": "STRICT_TRANS_TABLES",
            "fk_checks": 1,
            "triggers": list(EXPECTED_TRIGGERS),
        }
        result = await HealthService(settings()).ready(AsyncMock())
    payload = result.model_dump(mode="json")
    assert payload["databaseVersion"] == "8.0.14"
    assert payload["migrationRevision"] in migration_heads()
    assert payload["checkedAt"].endswith("Z")


async def test_new_schema_does_not_claim_legacy_application_is_ready():
    """新库建表成功也不能把尚未适配的旧业务代码标为可用。"""
    from app.core.exceptions import AppError

    with patch("app.services.health_service.read_database_state", new_callable=AsyncMock) as read:
        read.return_value = {
            "version": "8.0.14",
            "revisions": list(migration_heads()),
            "timezone": "+00:00",
            "sql_mode": "STRICT_TRANS_TABLES",
            "fk_checks": 1,
            "triggers": list(EXPECTED_TRIGGERS),
        }
        with pytest.raises(AppError) as error:
            await HealthService(settings()).ready(AsyncMock())
    assert error.value.error_code == "COMMUNITY_REFACTOR_PENDING"


def test_uniform_404_cors_and_validation_redaction():
    app = create_app(settings())

    @app.post("/test-validation")
    async def validate_body(payload: Annotated[dict, Body()]):
        return payload

    with TestClient(app) as client:
        response = client.get("/missing")
        assert response.status_code == response.json()["code"] == 404
        malformed = client.post(
            "/test-validation",
            content='{"password":"secret",',
            headers={"Content-Type": "application/json"},
        )
        assert malformed.status_code == 400
        assert "secret" not in malformed.text
        invalid = client.post("/test-validation", json="sensitive-input")
        assert invalid.status_code == 422
        assert "sensitive-input" not in invalid.text
        preflight = client.options(
            "/health/live",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert preflight.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"


def test_id_time_and_page_contract():
    class Example(Schema):
        entity_id: JsonId
        updated_at: UtcDateTime

    value = Example(entity_id=9223372036854775807, updated_at=datetime(2026, 10, 29, tzinfo=UTC))
    assert value.model_dump(mode="json")["entityId"] == "9223372036854775807"
    assert value.model_dump(mode="json")["updatedAt"].endswith("Z")
    with pytest.raises(ValidationError):
        PageParams(pageSize=101)


def test_unexpected_error_is_redacted_and_correlated():
    app = create_app(settings())

    @app.get("/test-error")
    async def fail():
        raise RuntimeError("PRIVATE_CONNECTION_STRING")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/test-error")
    assert response.status_code == 500
    assert "PRIVATE_CONNECTION_STRING" not in response.text
    assert response.json()["data"]["requestId"] == response.headers["x-request-id"]
