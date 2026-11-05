"""账号输入、密码与 JWT 的关键约束。"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from pydantic import ValidationError

from app.config.settings import Settings
from app.core.exceptions import AppError
from app.core.rate_limit import LoginRateLimiter
from app.core.security import AuthClaims, TokenService, hash_password, verify_password
from app.schemas.auth import LoginRequest, RegisterRequest
from app.schemas.user import AccountStatusUpdate, PasswordUpdate, ProfileUpdate
from app.services.user_service import UserService


def auth_settings() -> Settings:
    return Settings(_env_file=None, jwt_secret="unit-test-secret-" * 4, outbox_enabled=False)


async def test_avatar_reencodes_metadata_and_rejects_invalid_files(tmp_path):
    from io import BytesIO

    from PIL import Image, PngImagePlugin

    from app.services.avatar_service import AvatarStore

    store = AvatarStore(Settings(_env_file=None, avatar_storage_dir=tmp_path, avatar_size=64))
    source = BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("private", "must be stripped")
    Image.new("RGB", (80, 40), "red").save(source, format="PNG", pnginfo=metadata)

    async def stream(content):
        yield content[:10]
        yield content[10:]

    url = await store.save(stream(source.getvalue()))
    output = await store.read(url.rsplit("/", 1)[1])
    with Image.open(BytesIO(output)) as image:
        assert image.size == (64, 64) and image.format == "PNG"
        assert image.info == {}
    for invalid in (b"", b"<svg></svg>", source.getvalue()[:30]):
        with pytest.raises(AppError) as error:
            await store.save(stream(invalid))
        assert error.value.status_code == 422
    store.max_bytes = 5
    with pytest.raises(AppError) as error:
        await store.save(stream(source.getvalue()))
    assert error.value.status_code == 413
    store.max_bytes = 2 * 1024 * 1024
    store.max_pixels = 10
    with pytest.raises(AppError):
        await store.save(stream(source.getvalue()))
    for name in ("../secret", "abc.png", "A" * 32 + ".png"):
        with pytest.raises(AppError) as error:
            await store.read(name)
        assert error.value.status_code == 404
    await store.remove("https://example.com/avatar.png")
    assert len(list(tmp_path.iterdir())) == 1
    await store.remove(url)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("username", ["ab", "with space", "中文账号", "a" * 31])
def test_invalid_username_rejected(username):
    with pytest.raises(ValidationError):
        RegisterRequest(username=username, password="valid-password-123")


def test_password_spaces_removed_and_privileged_fields_rejected():
    request = RegisterRequest(username="Student_A", password=" valid-password ")
    assert request.password.get_secret_value() == "valid-password"
    with pytest.raises(ValidationError):
        RegisterRequest(username="student", password=" " * 12)
    with pytest.raises(ValidationError):
        RegisterRequest(username="student", password="valid-password-123", role="admin")
    with pytest.raises(ValidationError):
        ProfileUpdate(role="admin")
    with pytest.raises(ValidationError):
        ProfileUpdate(nickname=None)
    assert ProfileUpdate().model_fields_set == set()


def test_new_account_contract_normalizes_username_and_requires_nonempty_profile():
    from app.schemas.user import PrivacyUpdate

    data = RegisterRequest(username=" Student_A ", password="abcdef")
    assert data.username == "student_a"
    with pytest.raises(ValidationError):
        ProfileUpdate(nickname="   ")
    with pytest.raises(ValidationError):
        ProfileUpdate(avatarUrl="javascript:alert(1)")
    with pytest.raises(ValidationError):
        ProfileUpdate(avatarUrl="https://example.com/avatar.png")
    with pytest.raises(ValidationError):
        PrivacyUpdate(
            settingsVersion=1,
            publishPublic=1,
            checkinPublic=False,
            favoritePublic=False,
            learningPublic=False,
        )


@pytest.mark.parametrize("length", [6, 30])
def test_password_bounds_apply_after_removing_whitespace(length):
    value = " \t" + " ".join("a" * length) + "\n\u3000"
    for schema in (RegisterRequest, LoginRequest):
        assert (
            schema(username="student", password=value).password.get_secret_value() == "a" * length
        )
    request = PasswordUpdate(oldPassword=value, newPassword=value)
    assert request.old_password.get_secret_value() == "a" * length
    assert request.new_password.get_secret_value() == "a" * length


@pytest.mark.parametrize("value", ["", " \t\n\u3000", "12345", "x" * 31, "12 345"])
def test_password_outside_normalized_bounds_is_rejected(value):
    for schema in (RegisterRequest, LoginRequest):
        with pytest.raises(ValidationError):
            schema(username="student", password=value)
    for field in ("oldPassword", "newPassword"):
        with pytest.raises(ValidationError):
            PasswordUpdate(**{"oldPassword": "abcdef", "newPassword": "abcdef", field: value})


async def test_argon2_and_exact_password_verification():
    hashed = await hash_password(" valid-password ")
    assert hashed.startswith("$argon2id$")
    assert await verify_password(" valid-password ", hashed)
    assert not await verify_password("valid-password", hashed)
    assert not await verify_password("valid-password", "$argon2id$broken")


def test_token_requires_signature_issuer_audience_version_and_expiry():
    settings = auth_settings()
    service = TokenService(settings)
    key = "636cc709-c37b-4405-a867-822af3fac188"
    token = service.create(123, key)
    assert service.decode(token).user_id == 123
    assert service.decode(token).session_key == key
    assert service.decode(service.create(2**64 - 1, key)).user_id == 2**64 - 1
    claims = jwt.decode(token, options={"verify_signature": False})
    mutations = [
        {**claims, "exp": datetime.now(UTC) - timedelta(seconds=1)},
        {**claims, "iss": "another-app"},
        {**claims, "aud": "another-client"},
        {**claims, "sid": True},
        {key: value for key, value in claims.items() if key != "sid"},
        {**claims, "sid": "invalid-session"},
        {**claims, "sub": "invalid"},
        {**claims, "sub": "9" * 5000},
    ]
    for invalid in mutations:
        with pytest.raises(AppError) as error:
            service.decode(
                jwt.encode(invalid, settings.jwt_secret.get_secret_value(), algorithm="HS256")
            )
        assert error.value.status_code == 401
    with pytest.raises(AppError):
        service.decode(jwt.encode(claims, "different-key-" * 4, algorithm="HS256"))
    with pytest.raises(AppError):
        service.decode(
            jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm="HS384")
        )


def test_auth_configuration_preserves_database_secret_and_existing_key(tmp_path, monkeypatch):
    from dotenv import dotenv_values

    from scripts import configure_auth

    monkeypatch.setattr(configure_auth, "BACKEND_ROOT", tmp_path)
    path = tmp_path / ".env"
    path.write_text("DB_PASSWORD=synthetic-test-password\nJWT_SECRET=\n", encoding="utf-8")
    configure_auth.main()
    first = dotenv_values(path)
    assert first["DB_PASSWORD"] == "synthetic-test-password"
    assert len(first["JWT_SECRET"]) >= 32
    configure_auth.main()
    assert dotenv_values(path) == first


def test_missing_or_short_signing_key_is_not_accepted():
    with pytest.raises(AppError) as error:
        TokenService(Settings(_env_file=None, jwt_secret="")).create(1, 0)
    assert error.value.status_code == 503


def test_login_limit_has_bounded_storage_and_window_expiry():
    now = [100.0]
    limiter = LoginRateLimiter(limit=2, window_seconds=60, max_keys=2, clock=lambda: now[0])
    limiter.check("one")
    limiter.check("one")
    with pytest.raises(AppError) as error:
        limiter.check("one")
    assert error.value.status_code == 429
    now[0] += 61
    limiter.check("one")
    limiter.check("two")
    limiter.check("three")
    assert limiter.key_count <= 2


@pytest.mark.parametrize(
    "invalid", ["missing", "expired", "revoked", "other_user", "other_key", "disabled"]
)
def test_authentication_requires_current_database_session(invalid):
    from app.domain.account_policy import require_current_user

    key = "636cc709-c37b-4405-a867-822af3fac188"
    claims = AuthClaims(1, key)
    user = SimpleNamespace(id=1, status="active")
    login = SimpleNamespace(
        user_id=1,
        session_key=key,
        revoked_at=None,
        expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1),
    )
    if invalid == "missing":
        login = None
    elif invalid == "expired":
        login.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
    elif invalid == "revoked":
        login.revoked_at = datetime.now(UTC).replace(tzinfo=None)
    elif invalid == "other_user":
        login.user_id = 2
    elif invalid == "other_key":
        login.session_key = "other"
    elif invalid == "disabled":
        user.status = "disabled"
    with pytest.raises(AppError) as error:
        require_current_user(user, claims, login)
    assert error.value.status_code == 401


@pytest.mark.parametrize("status", ["active", "disabled"])
async def test_admin_status_change_revokes_sessions_and_audits_atomically(status):
    target = SimpleNamespace(
        id=2,
        role="user",
        status="disabled" if status == "active" else "active",
        nickname="学员",
        username="student",
        created_at=datetime.now(UTC),
    )
    session = MagicMock()
    service = UserService(session)
    service.locked_account = AsyncMock(return_value=target)
    service.audit = AsyncMock()
    claims = AuthClaims(1, "636cc709-c37b-4405-a867-822af3fac188")
    with patch("app.services.user_service.crud.revoke_sessions", AsyncMock()) as revoke:
        result = await service.set_account_status(
            claims,
            2,
            AccountStatusUpdate(
                status=status,
                expectedStatus=target.status,
            ),
        )
    assert result.status == status
    assert (target.deactivated_at is not None) == (status == "disabled")
    revoke.assert_awaited_once()
    service.audit.assert_awaited_once()


def test_admin_account_endpoints_validate_roles_and_never_return_passwords():
    from fastapi.testclient import TestClient

    from app.dependencies.auth import require_admin
    from app.dependencies.services import get_user_service
    from app.main import create_app
    from app.schemas.user import UserPublic
    from app.services.auth_service import AuthContext

    administrator = UserPublic(
        id=1,
        username="admin",
        nickname="管理员",
        role="admin",
        status="active",
        created_at=datetime.now(UTC),
    )
    created = UserPublic(
        id=2,
        username="new_user",
        nickname="新用户",
        role="admin",
        status="active",
        created_at=datetime.now(UTC),
    )
    service = SimpleNamespace(
        create_account=AsyncMock(return_value=created),
        reset_account_password=AsyncMock(return_value=None),
    )
    app = create_app(auth_settings())
    app.dependency_overrides[require_admin] = lambda: AuthContext(
        AuthClaims(1, "636cc709-c37b-4405-a867-822af3fac188"), administrator
    )
    app.dependency_overrides[get_user_service] = lambda: service
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/admin/users",
            json={"username": "new_user", "password": "abcdef", "role": "admin"},
        )
        assert response.status_code == 201
        assert response.json()["code"] == 201
        assert response.json()["data"]["status"] == "active"
        assert "password" not in response.text and "abcdef" not in response.text
        for extra in ({"role": "superadmin"}, {"status": "disabled"}):
            invalid = client.post(
                "/api/v1/admin/users", json={"username": "new_user", "password": "abcdef", **extra}
            )
            assert invalid.status_code == 422
    service.create_account.assert_awaited_once()
