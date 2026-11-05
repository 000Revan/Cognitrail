"""R02真实MySQL账号/会话/隐私闭环，仅连接显式独立测试库，精确清理本次账号。"""

import asyncio
import os
from dataclasses import dataclass, field
from datetime import timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete, func, or_, select, text, update

from app.config.enums import UserRole
from app.config.settings import Settings
from app.core.security import TokenService, utc_now
from app.database.crud.health import read_database_state
from app.database.models import AuditLog, User, UserAuthSession, UserPrivacySettings
from app.lifespan import lifespan
from app.main import create_app
from app.schemas.auth import RegisterRequest
from app.services.auth_service import AuthService

pytestmark = [
    pytest.mark.database,
    pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="需显式开启独立社区测试库"),
]
PASSWORD = "test-account-password-123"
NEW_PASSWORD = "updated-password-456"


async def test_public_relationship_lists_use_viewer_state_and_hide_private_counts(accounts):
    """关注双向列表与计数同源，当前查看者状态不借用主页作者身份。"""
    author_name, author = await accounts.register()
    viewer_name, viewer = await accounts.register()
    member_name, member = await accounts.register()
    owner_headers = headers(await accounts.login(author_name))
    viewer_headers = headers(await accounts.login(viewer_name))
    member_headers = headers(await accounts.login(member_name))
    for token, target in (
        (owner_headers, member),
        (viewer_headers, member),
        (viewer_headers, author),
        (member_headers, author),
    ):
        assert (
            await accounts.client.put(f"/api/v1/users/{target['id']}/follow", headers=token)
        ).status_code == 200
    base = f"/api/v1/users/{author['id']}"
    assert (await accounts.client.get(base + "/following")).status_code == 401
    response = await accounts.client.get(base + "/following", headers=viewer_headers)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["total"] == 1
    assert response.json()["data"]["items"][0]["id"] == member["id"]
    assert response.json()["data"]["items"][0]["isFollowing"] is True
    assert response.json()["data"]["items"][0]["canFollow"] is True
    followers = (await accounts.client.get(base + "/followers", headers=viewer_headers)).json()[
        "data"
    ]
    assert followers["total"] == 2
    self_row = next(row for row in followers["items"] if row["id"] == viewer["id"])
    assert self_row["canFollow"] is False and self_row["isFollowing"] is False
    one_page = (
        await accounts.client.get(
            base + "/followers", headers=viewer_headers, params={"pageSize": 1}
        )
    ).json()["data"]
    assert len(one_page["items"]) == 1 and one_page["total"] == 2
    last_page = (
        await accounts.client.get(
            base + "/followers", headers=viewer_headers, params={"pageSize": 1, "page": 999}
        )
    ).json()["data"]
    assert last_page["page"] == 2 and last_page["total"] == 2
    assert last_page["items"][0]["id"] != one_page["items"][0]["id"]
    assert (
        await accounts.client.get(base + "/followers", headers=viewer_headers, params={"page": 0})
    ).status_code == 422
    assert set(self_row) == {
        "id",
        "username",
        "nickname",
        "avatarUrl",
        "bio",
        "isFollowing",
        "canFollow",
    }
    profile = (await accounts.client.get(base + "/profile", headers=viewer_headers)).json()["data"]
    assert profile["favoriteCount"] is None and profile["learningCount"] is None
    assert profile["canViewFavorites"] is False and profile["canViewLearning"] is False
    own = (await accounts.client.get(base + "/profile", headers=owner_headers)).json()["data"]
    assert own["canViewFavorites"] is True and own["favoriteCount"] == 0
    assert own["canViewLearning"] is True and own["learningCount"] == 0
    async with accounts.app.state.database.sessions() as session, session.begin():
        await session.execute(
            update(User).where(User.id == int(member["id"])).values(status="disabled")
        )
    assert (await accounts.client.get(base + "/following", headers=viewer_headers)).json()["data"][
        "total"
    ] == 0
    assert (await accounts.client.get(base + "/followers", headers=viewer_headers)).json()["data"][
        "total"
    ] == 1
    profile = (await accounts.client.get(base + "/profile", headers=viewer_headers)).json()["data"]
    assert profile["followingCount"] == 0 and profile["followerCount"] == 1


async def test_follow_is_idempotent_and_does_not_expand_private_access(accounts):
    """关注并发幂等，禁止自关注；取消后动态来源立即移除。"""
    first, viewer = await accounts.register()
    second, target = await accounts.register()
    token = headers(await accounts.login(first))
    endpoint = f"/api/v1/users/{target['id']}/follow"
    assert (await accounts.client.put(endpoint)).status_code == 401
    assert (
        await accounts.client.put(f"/api/v1/users/{viewer['id']}/follow", headers=token)
    ).status_code == 403
    results = await asyncio.gather(
        *[accounts.client.put(endpoint, headers=token) for _ in range(3)]
    )
    assert all(r.status_code == 200 for r in results), [r.text for r in results]
    profile = (
        await accounts.client.get(f"/api/v1/users/{target['id']}/profile", headers=token)
    ).json()["data"]
    assert profile["isFollowing"] and profile["followerCount"] == 1
    following = (await accounts.client.get("/api/v1/users/me/following", headers=token)).json()[
        "data"
    ]
    assert following["total"] == 1 and following["items"][0]["id"] == target["id"]
    assert (
        await accounts.client.get(
            f"/api/v1/users/{target['id']}/collections?category=favorite", headers=token
        )
    ).json()["data"]["total"] == 0
    assert (await accounts.client.delete(endpoint, headers=token)).status_code == 200
    assert (await accounts.client.delete(endpoint, headers=token)).status_code == 200
    _, admin = await accounts.admin()
    assert (await accounts.client.put(endpoint, headers=headers(admin))).status_code == 403


def headers(token):
    return {"Authorization": f"Bearer {token}"}


async def cleanup_accounts(database, names, avatar_store=None):
    """只清理精确随机账号及其会话、隐私、账号审计，不匹配前缀删除真实数据。"""
    assert names and all(name.startswith("r02_") and len(name) >= 24 for name in names)
    async with database.sessions() as session, session.begin():
        avatar_urls = list(
            (await session.scalars(select(User.avatar_url).where(User.username.in_(names)))).all()
        )
        ids = list((await session.scalars(select(User.id).where(User.username.in_(names)))).all())
        if not ids:
            return
        from app.database.models import UserFollow

        await session.execute(
            delete(UserFollow).where(
                or_(UserFollow.follower_id.in_(ids), UserFollow.followee_id.in_(ids))
            )
        )
        await session.execute(
            delete(AuditLog).where(
                or_(
                    AuditLog.actor_id.in_(ids),
                    (AuditLog.target_type == "user") & AuditLog.target_id.in_(ids),
                )
            )
        )
        await session.execute(delete(UserAuthSession).where(UserAuthSession.user_id.in_(ids)))
        await session.execute(
            delete(UserPrivacySettings).where(UserPrivacySettings.user_id.in_(ids))
        )
        await session.execute(delete(User).where(User.id.in_(ids)))
    if avatar_store:
        for url in avatar_urls:
            await avatar_store.remove(url)


@dataclass
class AccountHarness:
    app: object
    client: httpx.AsyncClient
    names: set[str] = field(default_factory=set)

    def name(self):
        value = "r02_" + uuid4().hex[:24]
        self.names.add(value)
        return value

    async def register(self, name=None):
        name = name or self.name()
        self.names.add(name.lower())
        response = await self.client.post(
            "/api/v1/auth/register",
            json={
                "username": name,
                "password": PASSWORD,
            },
        )
        assert response.status_code == 201, response.text
        return name.lower(), response.json()["data"]

    async def login(self, name, password=PASSWORD):
        response = await self.client.post(
            "/api/v1/auth/login",
            json={
                "username": name,
                "password": password,
            },
        )
        assert response.status_code == 200, response.text
        return response.json()["data"]["accessToken"]

    async def admin(self):
        name = self.name()
        async with self.app.state.database.sessions() as session:
            user = await AuthService(session, TokenService(self.app.state.settings)).register(
                RegisterRequest(username=name, password=PASSWORD, nickname="测试管理员"),
                role=UserRole.ADMIN,
            )
        return user, await self.login(name)


@pytest_asyncio.fixture
async def accounts(tmp_path):
    """连接前校验测试目标，API提交后按精确ID清理，不接触开发库或旧库。"""
    settings = Settings(
        login_rate_limit=1000,
        jwt_secret="community-integration-test-secret-" * 2,
        avatar_storage_dir=tmp_path / "avatars",
        outbox_enabled=False,
    ).for_community_tests()
    app = create_app(settings)
    async with lifespan(app):
        async with app.state.database.sessions() as session:
            assert await session.scalar(text("SELECT DATABASE()")) == settings.db_name
            state = await read_database_state(session)
            assert state["version"].split("-")[0] == "8.0.14"
            assert state["revisions"] == ["c004_topic_privacy"]
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            harness = AccountHarness(app, client)
            try:
                yield harness
            finally:
                if harness.names:
                    await cleanup_accounts(app.state.database, harness.names)


async def test_registration_initializes_privacy_and_does_not_create_login_or_learning(accounts):
    name = accounts.name()
    _, user = await accounts.register(name.upper())
    assert user["username"] == user["nickname"] == name
    assert user["status"] == "active" and user["role"] == "user"
    assert not {"passwordHash", "authVersion", "sessionKey"} & user.keys()
    duplicate = await accounts.client.post(
        "/api/v1/auth/register",
        json={
            "username": " " + name.upper() + " ",
            "password": PASSWORD,
        },
    )
    assert duplicate.status_code == 409
    async with accounts.app.state.database.sessions() as session:
        privacy = await session.get(UserPrivacySettings, int(user["id"]))
        assert privacy.publish_public == 1
        assert privacy.checkin_public == privacy.favorite_public == privacy.learning_public == 0
        assert privacy.settings_version == 1
        assert (
            await session.scalar(
                select(func.count())
                .select_from(UserAuthSession)
                .where(UserAuthSession.user_id == int(user["id"]))
            )
            == 0
        )
    token = await accounts.login(name)
    profile = await accounts.client.patch(
        "/api/v1/users/me",
        headers=headers(token),
        json={
            "nickname": "路线探索者",
            "bio": "学习与分享",
        },
    )
    assert profile.status_code == 200
    assert profile.json()["data"]["bio"] == "学习与分享"
    for bad in (
        {"nickname": None},
        {"nickname": "  "},
        {"role": "admin"},
        {"status": "disabled"},
        {"avatarUrl": "javascript:alert(1)"},
        {"avatarUrl": "https://example.com/avatar.png"},
    ):
        assert (
            await accounts.client.patch("/api/v1/users/me", headers=headers(token), json=bad)
        ).status_code == 422


async def test_logout_revokes_only_current_persistent_session(accounts):
    name, user = await accounts.register()
    one, two = await accounts.login(name), await accounts.login(name)
    assert one != two
    response = await accounts.client.post("/api/v1/auth/logout", headers=headers(one))
    assert response.status_code == 200
    assert (await accounts.client.get("/api/v1/users/me", headers=headers(one))).status_code == 401
    assert (await accounts.client.get("/api/v1/users/me", headers=headers(two))).status_code == 200
    async with accounts.app.state.database.sessions() as session:
        logins = (
            await session.scalars(
                select(UserAuthSession).where(UserAuthSession.user_id == int(user["id"]))
            )
        ).all()
        assert len(logins) == 2
        assert sum(row.revoked_at is not None for row in logins) == 1
        assert all(
            row.session_key not in {one, two} and len(row.session_key) == 36 for row in logins
        )


async def test_avatar_upload_persists_replaces_and_rejects_invalid_input(accounts):
    from io import BytesIO

    from PIL import Image

    name, user = await accounts.register()
    assert user["avatarUrl"] is None
    token = await accounts.login(name)
    endpoint = "/api/v1/users/me/avatar"
    content = BytesIO()
    Image.new("RGB", (100, 80), "green").save(content, format="PNG")
    assert (await accounts.client.post(endpoint, content=content.getvalue())).status_code == 401
    first = await accounts.client.post(endpoint, headers=headers(token), content=content.getvalue())
    assert first.status_code == 200, first.text
    url = first.json()["data"]["avatarUrl"]
    image = await accounts.client.get(url)
    assert image.status_code == 200 and image.headers["content-type"] == "image/png"
    with Image.open(BytesIO(image.content)) as decoded:
        assert decoded.size == (512, 512)
    invalid = await accounts.client.post(endpoint, headers=headers(token), content=b"<svg/>")
    assert invalid.status_code == 422
    profile = await accounts.client.get("/api/v1/users/me", headers=headers(token))
    assert profile.json()["data"]["avatarUrl"] == url
    replaced = await accounts.client.post(
        endpoint, headers=headers(token), content=content.getvalue()
    )
    assert replaced.status_code == 200
    new_url = replaced.json()["data"]["avatarUrl"]
    assert new_url != url
    assert (await accounts.client.get(url)).status_code == 404
    assert (await accounts.client.get(new_url)).status_code == 200
    assert len(list(accounts.app.state.settings.avatar_storage_dir.iterdir())) == 1


async def test_avatar_failed_database_update_keeps_existing_image(accounts):
    from io import BytesIO

    from PIL import Image

    name, _ = await accounts.register()
    token = await accounts.login(name)
    content = BytesIO()
    Image.new("RGB", (10, 10)).save(content, format="PNG")
    endpoint = "/api/v1/users/me/avatar"
    first = await accounts.client.post(endpoint, headers=headers(token), content=content.getvalue())
    url = first.json()["data"]["avatarUrl"]
    with patch(
        "app.services.user_service.authenticated_account",
        AsyncMock(side_effect=RuntimeError("synthetic")),
    ):
        with pytest.raises(RuntimeError):
            await accounts.client.post(endpoint, headers=headers(token), content=content.getvalue())
    profile = await accounts.client.get("/api/v1/users/me", headers=headers(token))
    assert profile.json()["data"]["avatarUrl"] == url
    assert (await accounts.client.get(url)).status_code == 200
    assert len(list(accounts.app.state.settings.avatar_storage_dir.iterdir())) == 1


async def test_password_change_revokes_all_devices_without_automatic_login(accounts):
    name, _ = await accounts.register()
    one, two = await accounts.login(name), await accounts.login(name)
    url = "/api/v1/users/me/password"
    invalid = await accounts.client.patch(
        url,
        headers=headers(one),
        json={
            "oldPassword": "wrong-password",
            "newPassword": NEW_PASSWORD,
        },
    )
    assert invalid.status_code == 409
    assert (await accounts.client.get("/api/v1/users/me", headers=headers(two))).status_code == 200
    changed = await accounts.client.patch(
        url,
        headers=headers(one),
        json={
            "oldPassword": PASSWORD,
            "newPassword": NEW_PASSWORD,
        },
    )
    assert changed.status_code == 200
    for token in (one, two):
        assert (
            await accounts.client.get("/api/v1/users/me", headers=headers(token))
        ).status_code == 401
    assert (
        await accounts.client.post(
            "/api/v1/auth/login",
            json={
                "username": name,
                "password": PASSWORD,
            },
        )
    ).status_code == 401
    await accounts.login(name, NEW_PASSWORD)


async def test_privacy_version_conflict_and_user_isolation(accounts):
    name, user = await accounts.register()
    other, _ = await accounts.register()
    one, two = await accounts.login(name), await accounts.login(other)
    url = "/api/v1/users/me/privacy"
    assert (await accounts.client.get(url)).status_code == 401
    original = (await accounts.client.get(url, headers=headers(one))).json()["data"]
    assert original == {
        "topicPublic": False,
        "publishPublic": True,
        "checkinPublic": False,
        "favoritePublic": False,
        "learningPublic": False,
        "settingsVersion": 1,
    }
    changed = {**original, "checkinPublic": True}
    result = await accounts.client.patch(url, headers=headers(one), json=changed)
    assert result.status_code == 200 and result.json()["data"]["settingsVersion"] == 2
    stale = await accounts.client.patch(url, headers=headers(one), json=original)
    assert stale.status_code == 409
    assert stale.json()["data"]["errorCode"] == "PRIVACY_VERSION_CONFLICT"
    assert (await accounts.client.get(url, headers=headers(two))).json()["data"] == original
    for extra in (
        {"userId": user["id"]},
        {"settingsVersion": 0},
        {"settingsVersion": True},
        {"checkinPublic": 1},
    ):
        assert (
            await accounts.client.patch(
                url,
                headers=headers(two),
                json={
                    **original,
                    **extra,
                },
            )
        ).status_code == 422
    assert (
        await accounts.client.get(f"/api/v1/users/{user['id']}/privacy", headers=headers(two))
    ).status_code == 404


async def test_admin_account_management_revocation_and_audit(accounts):
    admin, admin_token = await accounts.admin()
    name, user = await accounts.register()
    old_one, old_two = await accounts.login(name), await accounts.login(name)
    assert (
        await accounts.client.get("/api/v1/admin/users", headers=headers(old_one))
    ).status_code == 403
    root = "/api/v1/admin/users"
    managed_name = accounts.name()
    created = await accounts.client.post(
        root,
        headers=headers(admin_token),
        json={
            "username": managed_name,
            "password": PASSWORD,
            "role": "admin",
        },
    )
    assert created.status_code == 201
    managed = created.json()["data"]
    assert managed["role"] == "admin" and managed["nickname"] == managed_name
    target = root + "/" + user["id"]
    changed = await accounts.client.patch(
        target,
        headers=headers(admin_token),
        json={
            "nickname": "新昵称",
            "expectedNickname": user["nickname"],
        },
    )
    assert changed.status_code == 200
    assert (
        await accounts.client.patch(
            target,
            headers=headers(admin_token),
            json={
                "nickname": "过期修改",
                "expectedNickname": user["nickname"],
            },
        )
    ).status_code == 409
    disabled = await accounts.client.patch(
        target + "/status",
        headers=headers(admin_token),
        json={
            "status": "disabled",
            "expectedStatus": "active",
        },
    )
    assert disabled.status_code == 200
    for token in (old_one, old_two):
        assert (
            await accounts.client.get("/api/v1/users/me", headers=headers(token))
        ).status_code == 401
    assert (
        await accounts.client.post(
            "/api/v1/auth/login",
            json={
                "username": name,
                "password": PASSWORD,
            },
        )
    ).status_code == 401
    assert (
        await accounts.client.patch(
            target + "/status",
            headers=headers(admin_token),
            json={
                "status": "active",
                "expectedStatus": "disabled",
            },
        )
    ).status_code == 200
    assert (
        await accounts.client.get("/api/v1/users/me", headers=headers(old_one))
    ).status_code == 401
    current = await accounts.login(name)
    reset = await accounts.client.post(
        target + "/reset-password", headers=headers(admin_token), json={"newPassword": NEW_PASSWORD}
    )
    assert reset.status_code == 200
    assert (
        await accounts.client.get("/api/v1/users/me", headers=headers(current))
    ).status_code == 401
    await accounts.login(name, NEW_PASSWORD)
    for suffix, payload in (
        ("/status", {"status": "disabled", "expectedStatus": "active"}),
        ("/reset-password", {"newPassword": NEW_PASSWORD}),
    ):
        method = "PATCH" if suffix == "/status" else "POST"
        protected = await accounts.client.request(
            method, root + "/" + str(admin.id) + suffix, headers=headers(admin_token), json=payload
        )
        assert protected.status_code == 409
    assert (
        await accounts.client.post(
            root,
            headers=headers(old_one),
            json={
                "username": accounts.name(),
                "password": PASSWORD,
                "role": "admin",
            },
        )
    ).status_code == 401
    async with accounts.app.state.database.sessions() as session:
        audits = (
            await session.scalars(select(AuditLog).where(AuditLog.actor_id == admin.id))
        ).all()
        assert len(audits) >= 5
        assert all(
            PASSWORD not in str(row.details) and admin_token not in str(row.details)
            for row in audits
        )
        assert await session.get(UserPrivacySettings, int(managed["id"])) is not None


async def test_signed_token_still_requires_own_unexpired_session_and_current_role(accounts):
    name, user = await accounts.register()
    other, _ = await accounts.register()
    token, other_token = await accounts.login(name), await accounts.login(other)
    tokens = TokenService(accounts.app.state.settings)
    forged_reference = tokens.create(int(user["id"]), tokens.decode(other_token).session_key)
    assert (
        await accounts.client.get("/api/v1/users/me", headers=headers(forged_reference))
    ).status_code == 401
    async with accounts.app.state.database.sessions() as session, session.begin():
        await session.execute(
            update(UserAuthSession)
            .where(UserAuthSession.session_key == tokens.decode(token).session_key)
            .values(
                issued_at=utc_now() - timedelta(hours=2), expires_at=utc_now() - timedelta(hours=1)
            )
        )
    assert (
        await accounts.client.get("/api/v1/users/me", headers=headers(token))
    ).status_code == 401
    admin, admin_token = await accounts.admin()
    async with accounts.app.state.database.sessions() as session, session.begin():
        await session.execute(update(User).where(User.id == admin.id).values(role="user"))
    assert (
        await accounts.client.get("/api/v1/admin/users", headers=headers(admin_token))
    ).status_code == 403


async def test_registration_privacy_failure_rolls_back_entire_account(accounts):
    name = accounts.name()
    with patch(
        "app.services.auth_service.crud.add_privacy",
        AsyncMock(side_effect=RuntimeError("synthetic")),
    ):
        with pytest.raises(RuntimeError):
            await accounts.client.post(
                "/api/v1/auth/register", json={"username": name, "password": PASSWORD}
            )
    async with accounts.app.state.database.sessions() as session:
        assert (
            await session.scalar(
                select(func.count()).select_from(User).where(User.username == name)
            )
            == 0
        )


async def test_concurrent_registration_and_privacy_updates_do_not_duplicate_or_overwrite(accounts):
    name = accounts.name()
    registered = await asyncio.gather(
        *[
            accounts.client.post(
                "/api/v1/auth/register", json={"username": name, "password": PASSWORD}
            )
            for _ in range(2)
        ]
    )
    assert sorted(response.status_code for response in registered) == [201, 409]
    token = await accounts.login(name)
    url = "/api/v1/users/me/privacy"
    current = (await accounts.client.get(url, headers=headers(token))).json()["data"]
    responses = await asyncio.gather(
        *[
            accounts.client.patch(url, headers=headers(token), json={**current, field: True})
            for field in ("checkinPublic", "favoritePublic")
        ]
    )
    assert sorted(response.status_code for response in responses) == [200, 409]


async def test_concurrent_old_password_login_cannot_survive_password_change(accounts):
    name, _ = await accounts.register()
    token = await accounts.login(name)
    login, changed = await asyncio.gather(
        accounts.client.post("/api/v1/auth/login", json={"username": name, "password": PASSWORD}),
        accounts.client.patch(
            "/api/v1/users/me/password",
            headers=headers(token),
            json={"oldPassword": PASSWORD, "newPassword": NEW_PASSWORD},
        ),
    )
    assert changed.status_code == 200 and login.status_code in (200, 401)
    if login.status_code == 200:
        assert (
            await accounts.client.get(
                "/api/v1/users/me", headers=headers(login.json()["data"]["accessToken"])
            )
        ).status_code == 401
    await accounts.login(name, NEW_PASSWORD)
