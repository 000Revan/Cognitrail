"""R03真实独立MySQL：稳定身份、原子发布、幂等、权限与作者仓库。"""

import asyncio
import copy
import os
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.database.models import (
    ActivityEvent,
    LearningNode,
    NotificationOutbox,
    ReleaseNode,
    ReleaseResource,
    ReleaseStageEdge,
    RoadmapRelease,
    SkillRoadmap,
)
from tests.integration.test_accounts import accounts as accounts  # noqa: F401
from tests.integration.test_accounts import headers
from tests.route_cleanup import cleanup_routes

pytestmark = [
    pytest.mark.database,
    pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="需显式独立测试库"),
]


@pytest_asyncio.fixture
async def routes(accounts):
    try:
        yield accounts
    finally:
        if accounts.names:
            await cleanup_routes(accounts.app.state.database, accounts.names)


def graph(version=1):
    """完整可发布工作稿，资源与连线均使用临时ID。"""
    return {
        "title": "Python路线",
        "description": "面向初学者，从基础到实践",
        "licenseCode": "UNLICENSED",
        "effortNote": None,
        "expectedVersion": version,
        "stages": [
            {
                "id": "tmp_s1",
                "title": "基础",
                "nodes": [
                    {
                        "id": "tmp_n1",
                        "title": "变量",
                        "content": "PRIVATE_BODY_V1",
                        "resources": [
                            {
                                "id": "tmp_r1",
                                "title": "官方教程",
                                "resourceType": "article",
                                "resourceUrl": "https://example.com/v1",
                            }
                        ],
                    }
                ],
            },
            {
                "id": "tmp_s2",
                "title": "项目",
                "nodes": [
                    {
                        "id": "tmp_n2",
                        "title": "练习",
                        "content": "完成练习",
                        "resources": [
                            {
                                "id": "tmp_r2",
                                "title": "练习资源",
                                "resourceType": "video",
                                "resourceUrl": "https://example.com/project",
                            }
                        ],
                    }
                ],
            },
        ],
        "connections": [{"source": "tmp_s1", "target": "tmp_s2"}],
    }


async def author(routes):
    name, _ = await routes.register()
    token = await routes.login(name)
    response = await routes.client.post(
        "/api/v1/roadmaps", headers=headers(token), json={"title": "Python路线"}
    )
    assert response.status_code == 201, response.text
    assert response.json()["code"] == 201
    route_id = response.json()["data"]["id"]
    return token, route_id


async def save(routes, token, route_id, data):
    response = await routes.client.put(
        f"/api/v1/roadmaps/{route_id}/draft", headers=headers(token), json=data
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["document"]


async def publish(routes, token, route_id, document, summary="首次发布"):
    return await routes.client.post(
        f"/api/v1/roadmaps/{route_id}/publish",
        headers=headers(token),
        json={"expectedVersion": document["expectedVersion"], "updateSummary": summary},
    )


async def test_admin_review_filters_frozen_versions_and_governance_preserves_learning(routes):
    """审核与普通社区隔离，治理覆盖全部快照并保持本人历史。"""
    from app.database.models import ModerationAction

    token, rid = await author(routes)
    doc = await save(routes, token, rid, graph())
    published = (await publish(routes, token, rid, doc)).json()["data"]
    reader_name, _ = await routes.register()
    reader = headers(await routes.login(reader_name))
    enrolled = (
        await routes.client.post(
            f"/api/v1/roadmaps/{rid}/enroll",
            headers=reader,
            json={"releaseId": published["releaseId"]},
        )
    ).json()["data"]
    doc["title"] = "UNPUBLISHED_SECRET"
    await save(routes, token, rid, doc)
    _, admin = await routes.admin()
    admin_headers = headers(admin)
    endpoint = f"/api/v1/admin/roadmaps/{rid}"
    assert (await routes.client.get(endpoint, headers=reader)).status_code == 403
    result = (await routes.client.get(endpoint, headers=admin_headers)).json()["data"]
    assert result["title"] == "Python路线"
    assert "PRIVATE_BODY_V1" in str(result) and "UNPUBLISHED_SECRET" not in str(result)
    assert not result["canFavorite"] and not result["canStartLearning"]
    listing = await routes.client.get(
        "/api/v1/admin/roadmaps?keyword=Python&difficulty=beginner&sortBy=title&order=asc",
        headers=admin_headers,
    )
    assert rid in [r["id"] for r in listing.json()["data"]["items"]]
    hidden = await routes.client.get(
        "/api/v1/admin/roadmaps?keyword=UNPUBLISHED_SECRET", headers=admin_headers
    )
    assert hidden.json()["data"]["total"] == 0
    assert (
        await routes.client.get(endpoint + "?releaseId=999999999", headers=admin_headers)
    ).status_code == 404
    payload = {"expectedVersion": result["editVersion"], "reason": "审核发现不适当内容"}
    disabled = await routes.client.post(endpoint + "/disable", headers=admin_headers, json=payload)
    assert disabled.status_code == 200, disabled.text
    assert (await routes.client.get(f"/api/v1/roadmaps/{rid}")).status_code == 404
    assert (
        await routes.client.get(f"/api/v1/enrollments/{enrolled['id']}/content", headers=reader)
    ).status_code == 409
    assert (
        await routes.client.get(f"/api/v1/enrollments/{enrolled['id']}", headers=reader)
    ).status_code == 200
    assert (await routes.client.get(endpoint, headers=admin_headers)).status_code == 200
    assert (
        await routes.client.post(endpoint + "/restore", headers=admin_headers, json=payload)
    ).status_code == 409
    payload["expectedVersion"] = disabled.json()["data"]["editVersion"]
    restored = await routes.client.post(endpoint + "/restore", headers=admin_headers, json=payload)
    assert restored.status_code == 200, restored.text
    assert (
        await routes.client.get(f"/api/v1/enrollments/{enrolled['id']}/content", headers=reader)
    ).status_code == 200
    async with routes.app.state.database.sessions() as session:
        actions = list(
            await session.scalars(
                select(ModerationAction)
                .where(
                    ModerationAction.target_type == "roadmap",
                    ModerationAction.target_id == int(rid),
                )
                .order_by(ModerationAction.id)
            )
        )
        assert [a.action for a in actions] == ["disable", "restore"]


async def test_admin_cannot_participate_in_community_and_official_content_is_shared(routes):
    """管理账号仅维护官方路线，另一管理员可继续维护，普通用户无维护权限。"""
    _, admin = await routes.admin()
    _, second = await routes.admin()
    owner, private_id = await author(routes)
    for method, path, body in [
        ("GET", "/api/v1/roadmaps", None),
        ("GET", "/api/v1/users/me/favorites", None),
        ("GET", "/api/v1/users/me/enrollments", None),
        ("PUT", f"/api/v1/roadmaps/{private_id}/favorite", None),
        ("POST", f"/api/v1/roadmaps/{private_id}/enroll", {"releaseId": "1"}),
        ("GET", f"/api/v1/roadmaps/{private_id}/issues", None),
        ("POST", "/api/v1/roadmaps", {"title": "个人路线"}),
    ]:
        response = await routes.client.request(method, path, headers=headers(admin), json=body)
        assert response.status_code == 403, response.text
    assert (
        await routes.client.get(f"/api/v1/admin/roadmaps/{private_id}", headers=headers(admin))
    ).status_code == 404
    assert (
        await routes.client.get(f"/api/v1/roadmaps/{private_id}/draft", headers=headers(admin))
    ).status_code == 404
    forbidden = await routes.client.post(
        "/api/v1/roadmaps",
        headers=headers(owner),
        json={"title": "伪造官方", "roadmapType": "official"},
    )
    assert forbidden.status_code == 403
    created = await routes.client.post(
        "/api/v1/roadmaps",
        headers=headers(admin),
        json={"title": "官方路线", "roadmapType": "official"},
    )
    assert created.status_code == 201, created.text
    rid = created.json()["data"]["id"]
    doc = await save(routes, second, rid, graph())
    assert (await publish(routes, second, rid, doc)).status_code == 200
    detail = await routes.client.get(
        f"/api/v1/roadmaps/{rid}?preview=draft", headers=headers(second)
    )
    assert detail.json()["data"]["canMaintain"]
    official = (
        await routes.client.get("/api/v1/admin/official-roadmaps", headers=headers(second))
    ).json()["data"]
    assert rid in [r["id"] for r in official["items"]]
    community = (await routes.client.get("/api/v1/admin/roadmaps", headers=headers(second))).json()[
        "data"
    ]
    assert rid not in [r["id"] for r in community["items"]]
    system = await routes.client.get("/api/v1/admin/system", headers=headers(second))
    assert system.status_code == 200 and "password" not in system.text.lower()


async def test_author_detail_has_real_engagement_and_release_summary(routes):
    token, rid = await author(routes)
    doc = await save(routes, token, rid, graph())
    published = (await publish(routes, token, rid, doc)).json()["data"]
    name, _ = await routes.register()
    reader = headers(await routes.login(name))
    base = f"/api/v1/roadmaps/{rid}"
    assert (await routes.client.put(base + "/favorite", headers=reader)).status_code == 200
    assert (
        await routes.client.post(
            base + "/enroll", headers=reader, json={"releaseId": published["releaseId"]}
        )
    ).status_code == 200
    result = (await routes.client.get(base + "?preview=draft", headers=headers(token))).json()[
        "data"
    ]
    assert result["learnerCount"] == result["favoriteCount"] == 1
    assert result["updateSummary"] == "首次发布"
    assert not result["canFavorite"] and not result["canStartLearning"]


async def test_live_working_copy_does_not_change_snapshot_and_repository_is_single(routes):
    token, rid = await author(routes)
    source = graph()
    source["stages"][0]["nodes"][0]["resources"][0].update(languageCode="zh-CN", accessType="free")
    doc = await save(routes, token, rid, source)
    node = doc["stages"][0]["nodes"][0]
    stable, revision = node["stableKey"], node["revisionNo"]
    original = copy.deepcopy(doc)
    first = await publish(routes, token, rid, doc)
    assert first.status_code == 200, first.text
    release_id = int(first.json()["data"]["releaseId"])
    # 发布不递增工作稿修订，原请求可重放。
    again = await publish(routes, token, rid, doc)
    assert again.json()["data"] == first.json()["data"]
    different = await publish(routes, token, rid, doc, "另一个说明")
    assert different.status_code == 409
    doc["title"] = "Python路线新版"
    doc["effortNote"] = "每周3小时"
    doc["licenseCode"] = "CC-BY-4.0"
    moved = doc["stages"][0]["nodes"].pop()
    moved["title"] = "变量与类型"
    moved["resources"][0]["resourceUrl"] = "https://example.com/replacement"
    doc["stages"][1]["nodes"].append(moved)
    doc["stages"][0]["nodes"].append(doc["stages"][1]["nodes"].pop(0))
    doc = await save(routes, token, rid, doc)
    assert doc["stages"][1]["nodes"][0]["stableKey"] == stable
    assert doc["stages"][1]["nodes"][0]["revisionNo"] == revision
    async with routes.app.state.database.sessions() as session:
        head = await session.get(SkillRoadmap, int(rid))
        frozen = await session.get(RoadmapRelease, release_id)
        assert head.current_release_id == release_id
        assert frozen.title == "Python路线" and frozen.effort_note is None
        assert frozen.license_code == "UNLICENSED"
        frozen_node = await session.scalar(
            select(ReleaseNode).where(
                ReleaseNode.release_id == release_id, ReleaseNode.stable_key == stable
            )
        )
        assert frozen_node.title == "变量" and frozen_node.content == "PRIVATE_BODY_V1"
        resource = await session.scalar(
            select(ReleaseResource).where(ReleaseResource.node_id == frozen_node.id)
        )
        assert resource.url == "https://example.com/v1"
        assert resource.language_code == "zh-CN" and resource.access_type == "free"
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ReleaseStageEdge)
                .where(ReleaseStageEdge.release_id == release_id)
            )
            == 1
        )
    listing = await routes.client.get("/api/v1/roadmaps/mine", headers=headers(token))
    items = listing.json()["data"]["items"]
    assert len(items) == 1 and items[0]["hasUnpublishedChanges"]
    assert items[0]["publishedTitle"] == "Python路线"
    conflict = await routes.client.put(
        f"/api/v1/roadmaps/{rid}/draft", headers=headers(token), json=original
    )
    assert conflict.status_code == 409
    semantic = doc["stages"][1]["nodes"][0]
    semantic["changePolicy"] = "reconfirm"
    semantic["content"] = "学习目标实质变化"
    doc = await save(routes, token, rid, doc)
    assert doc["stages"][1]["nodes"][0]["revisionNo"] == revision + 1
    no_op = await save(routes, token, rid, doc)
    assert no_op == doc
    result = await publish(routes, token, rid, doc, "更新目标")
    assert result.status_code == 200, result.text
    assert result.json()["data"]["versionNo"] == 2
    # 已发布节点软删除后，原身份仍在工作稿表且历史发布不变。
    removed_id = int(doc["stages"][1]["nodes"][0]["id"])
    doc["stages"].pop()
    doc["connections"] = []
    await save(routes, token, rid, doc)
    async with routes.app.state.database.sessions() as session:
        removed = await session.get(LearningNode, removed_id)
        assert removed.is_deleted == 1 and removed.stable_key == stable
        assert await session.get(RoadmapRelease, release_id)


async def test_concurrent_publish_is_idempotent_and_events_are_atomic(routes):
    token, rid = await author(routes)
    doc = await save(routes, token, rid, graph())
    replies = await asyncio.gather(*[publish(routes, token, rid, doc) for _ in range(3)])
    assert all(r.status_code == 200 for r in replies), [r.text for r in replies]
    assert len({r.json()["data"]["releaseId"] for r in replies}) == 1
    doc["title"] = "第二版工作稿"
    doc = await save(routes, token, rid, doc)
    async with routes.app.state.database.sessions() as session:
        old_pointer = (await session.get(SkillRoadmap, int(rid))).current_release_id
    # 注入快照末尾事件构造失败，验证所有已flush快照和指针均回滚。
    with patch(
        "app.services.roadmap_service.NotificationOutbox",
        side_effect=RuntimeError("injected-publish-failure"),
    ):
        with pytest.raises(RuntimeError, match="injected-publish-failure"):
            await publish(routes, token, rid, doc, "第二版")
    async with routes.app.state.database.sessions() as session:
        head = await session.get(SkillRoadmap, int(rid))
        assert head.current_release_id == old_pointer
        for model in (RoadmapRelease, ActivityEvent):
            assert (
                await session.scalar(
                    select(func.count()).select_from(model).where(model.roadmap_id == int(rid))
                )
                == 1
            )
        keys = select(ActivityEvent.event_key).where(ActivityEvent.roadmap_id == int(rid))
        assert (
            await session.scalar(
                select(func.count())
                .select_from(NotificationOutbox)
                .where(NotificationOutbox.event_key.in_(keys))
            )
            == 1
        )
    result = await publish(routes, token, rid, doc, "第二版")
    assert result.status_code == 200 and result.json()["data"]["versionNo"] == 2


async def test_draft_delete_archive_restore_permissions_and_validation(routes):
    token, rid = await author(routes)
    name, _ = await routes.register()
    other = await routes.login(name)
    _, admin_token = await routes.admin()
    for intruder in (other, admin_token):
        response = await routes.client.get(
            f"/api/v1/roadmaps/{rid}/draft", headers=headers(intruder)
        )
        assert response.status_code == 404
    empty = await routes.client.post(
        f"/api/v1/roadmaps/{rid}/publish",
        headers=headers(token),
        json={"expectedVersion": 1, "updateSummary": "发布"},
    )
    assert empty.status_code == 422
    doc = await save(routes, token, rid, graph())
    forged = copy.deepcopy(doc)
    forged["stages"][0]["nodes"][0]["revisionNo"] = 999
    conflict = await routes.client.put(
        f"/api/v1/roadmaps/{rid}/draft", headers=headers(token), json=forged
    )
    assert conflict.status_code == 409
    # 真实外链白名单。
    forged = copy.deepcopy(doc)
    forged["stages"][0]["nodes"][0]["resources"][0]["resourceUrl"] = "javascript:alert(1)"
    assert (
        await routes.client.put(
            f"/api/v1/roadmaps/{rid}/draft", headers=headers(token), json=forged
        )
    ).status_code == 422
    await publish(routes, token, rid, doc)
    assert (
        await routes.client.request(
            "DELETE",
            f"/api/v1/roadmaps/{rid}",
            headers=headers(token),
            json={"expectedVersion": doc["expectedVersion"]},
        )
    ).status_code == 409
    for action, status in (("archive", "archived"), ("restore", "published")):
        response = await routes.client.post(
            f"/api/v1/roadmaps/{rid}/{action}",
            headers=headers(token),
            json={"expectedVersion": doc["expectedVersion"]},
        )
        assert response.status_code == 200
        async with routes.app.state.database.sessions() as session:
            head = await session.get(SkillRoadmap, int(rid))
            assert head.distribution_status == status
            assert head.current_release_id is not None
        if action == "archive":
            response = await routes.client.put(
                f"/api/v1/roadmaps/{rid}/draft", headers=headers(token), json=doc
            )
            assert response.status_code == 409


async def test_safe_delete_cleans_graph_and_unpublished_external_ids_are_rejected(routes):
    token, rid = await author(routes)
    doc = await save(routes, token, rid, graph())
    other_token, other_id = await author(routes)
    forged = graph()
    forged["stages"][0]["id"] = doc["stages"][0]["id"]
    forged["connections"] = []
    assert (
        await routes.client.put(
            f"/api/v1/roadmaps/{other_id}/draft", headers=headers(other_token), json=forged
        )
    ).status_code == 409
    result = await routes.client.request(
        "DELETE",
        f"/api/v1/roadmaps/{rid}",
        headers=headers(token),
        json={"expectedVersion": doc["expectedVersion"]},
    )
    assert result.status_code == 200
    async with routes.app.state.database.sessions() as session:
        assert await session.get(SkillRoadmap, int(rid)) is None


async def test_unchanged_snapshot_does_not_create_version_and_blocked_content_cannot_publish(
    routes,
):
    token, rid = await author(routes)
    doc = await save(routes, token, rid, graph())
    first = await publish(routes, token, rid, doc)
    # 规范化后相同内容，即使产生新工作稿修订也不重复造快照。
    doc["effortNote"] = "   "
    doc = await save(routes, token, rid, doc)
    repeated = await publish(routes, token, rid, doc, "相同内容")
    assert repeated.status_code == 200
    assert repeated.json()["data"]["releaseId"] == first.json()["data"]["releaseId"]
    async with routes.app.state.database.sessions() as session, session.begin():
        head = await session.get(SkillRoadmap, int(rid))
        head.moderation_status = "disabled"
    blocked = await publish(routes, token, rid, doc)
    assert blocked.status_code == 409
    assert (
        await routes.client.get(f"/api/v1/roadmaps/{rid}/draft", headers=headers(token))
    ).status_code == 403


async def test_public_snapshot_and_favorite_are_independent_of_learning(routes):
    """公开摘要、收藏和登录都不泄漏正文或创建学习状态。"""
    from app.database.models import LearningSession, RoadmapCheckin, UserNodeProgress, UserRoadmap

    token, rid = await author(routes)
    doc = await save(routes, token, rid, graph())
    assert (await publish(routes, token, rid, doc)).status_code == 200
    name, _ = await routes.register()
    reader = await routes.login(name)
    for credential in (None, reader, token):
        response = await routes.client.get(
            f"/api/v1/roadmaps/{rid}", headers=headers(credential) if credential else {}
        )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["title"] == "Python路线" and data["versionNo"] == 1
        assert data["canReadContent"] is False
        assert data["stages"][0]["nodes"][0]["title"] == "变量"
        assert "content" not in data["stages"][0]["nodes"][0]
        assert "resources" not in data["stages"][0]["nodes"][0]
        assert "PRIVATE_BODY_V1" not in response.text and "example.com" not in response.text
    assert (await routes.client.put(f"/api/v1/roadmaps/{rid}/favorite")).status_code == 401
    assert (
        await routes.client.put(f"/api/v1/roadmaps/{rid}/favorite", headers=headers(token))
    ).status_code == 403
    for _ in range(2):
        result = await routes.client.put(
            f"/api/v1/roadmaps/{rid}/favorite", headers=headers(reader)
        )
        assert result.status_code == 200, result.text
        assert result.json()["data"]["favoriteCount"] == 1
    listing = await routes.client.get("/api/v1/roadmaps", params={"q": "Python"})
    assert listing.status_code == 200, listing.text
    card = next(i for i in listing.json()["data"]["items"] if i["id"] == rid)
    assert card["favoriteCount"] == 1 and card["learnerCount"] == 0
    assert card["stageCount"] == card["nodeCount"] == 2
    doc["title"] = "UNPUBLISHED_PRIVATE_TITLE"
    doc = await save(routes, token, rid, doc)
    public = await routes.client.get(f"/api/v1/roadmaps/{rid}", headers=headers(token))
    assert public.json()["data"]["title"] == "Python路线"
    preview = await routes.client.get(
        f"/api/v1/roadmaps/{rid}?preview=draft", headers=headers(token)
    )
    assert preview.json()["data"]["title"] == "UNPUBLISHED_PRIVATE_TITLE"
    assert preview.json()["data"]["canReadContent"] is True
    assert (
        await routes.client.get(f"/api/v1/roadmaps/{rid}?preview=draft", headers=headers(reader))
    ).status_code == 404
    assert (await routes.client.get(f"/api/v1/roadmaps/{rid}?preview=draft")).status_code == 401
    assert (await publish(routes, token, rid, doc, "第二版")).status_code == 200
    favorites = await routes.client.get("/api/v1/users/me/favorites", headers=headers(reader))
    assert favorites.json()["data"]["items"][0]["roadmap"]["versionNo"] == 2
    async with routes.app.state.database.sessions() as session:
        relation_ids = select(UserRoadmap.id).where(UserRoadmap.roadmap_id == int(rid))
        session_ids = select(LearningSession.id).where(LearningSession.roadmap_id == int(rid))
        for model, condition in (
            (UserRoadmap, UserRoadmap.roadmap_id == int(rid)),
            (LearningSession, LearningSession.roadmap_id == int(rid)),
            (UserNodeProgress, UserNodeProgress.session_id.in_(session_ids)),
            (RoadmapCheckin, RoadmapCheckin.user_roadmap_id.in_(relation_ids)),
        ):
            assert (
                await session.scalar(select(func.count()).select_from(model).where(condition)) == 0
            )


async def test_restricted_favorites_hide_content_and_allow_removal(routes):
    """归档、下架和快照受限均退出发现，收藏只保留安全占位及取消。"""
    from app.database.models import User

    token, rid = await author(routes)
    doc = await save(routes, token, rid, graph())
    await publish(routes, token, rid, doc)
    name, _ = await routes.register()
    reader = await routes.login(name)
    assert (
        await routes.client.put(f"/api/v1/roadmaps/{rid}/favorite", headers=headers(reader))
    ).status_code == 200
    for mode in ("archive", "moderated", "restricted", "author_disabled"):
        async with routes.app.state.database.sessions() as session, session.begin():
            route = await session.get(SkillRoadmap, int(rid))
            release = await session.get(RoadmapRelease, route.current_release_id)
            owner = await session.get(User, route.creator_id)
            route.distribution_status = "archived" if mode == "archive" else "published"
            route.author_archived_at = None
            route.moderation_status = "disabled" if mode == "moderated" else "normal"
            release.content_access = "restricted" if mode == "restricted" else "normal"
            owner.status = "disabled" if mode == "author_disabled" else "active"
        public = await routes.client.get(f"/api/v1/roadmaps/{rid}")
        assert public.status_code == 404
        listing = await routes.client.get("/api/v1/roadmaps")
        assert listing.status_code == 200, listing.text
        assert rid not in [i["id"] for i in listing.json()["data"]["items"]]
        favorites = await routes.client.get("/api/v1/users/me/favorites", headers=headers(reader))
        item = favorites.json()["data"]["items"][0]
        assert item["roadmap"] is None and item["accessible"] is False
        assert "Python路线" not in favorites.text and "PRIVATE_BODY" not in favorites.text
        assert (
            await routes.client.put(f"/api/v1/roadmaps/{rid}/favorite", headers=headers(reader))
        ).status_code == 404
    result = await routes.client.delete(f"/api/v1/roadmaps/{rid}/favorite", headers=headers(reader))
    assert result.status_code == 200 and result.json()["data"]["favoriteCount"] == 0
    assert (
        await routes.client.delete(f"/api/v1/roadmaps/{rid}/favorite", headers=headers(reader))
    ).status_code == 404


async def test_discovery_search_sort_pagination_and_concurrent_favorites(routes):
    """全结果排序后分页；独立计数不被JOIN放大，未发布工作稿不参与搜索。"""
    token, first_id = await author(routes)
    ids = [first_id]
    for _ in range(2):
        created = await routes.client.post(
            "/api/v1/roadmaps", headers=headers(token), json={"title": "待编辑"}
        )
        ids.append(created.json()["data"]["id"])
    keyword = "R04_" + first_id
    documents = []
    for index, rid in enumerate(ids):
        source = graph()
        source["title"] = keyword + f"_{index}"
        source["difficulty"] = "advanced" if index == 1 else "beginner"
        doc = await save(routes, token, rid, source)
        await publish(routes, token, rid, doc)
        documents.append(doc)
    name, _ = await routes.register()
    reader = await routes.login(name)
    replies = await asyncio.gather(
        *[
            routes.client.put(f"/api/v1/roadmaps/{ids[0]}/favorite", headers=headers(reader))
            for _ in range(3)
        ]
    )
    assert all(r.status_code == 200 and r.json()["data"]["favoriteCount"] == 1 for r in replies)
    name2, _ = await routes.register()
    reader2 = await routes.login(name2)
    for rid in ids[:2]:
        assert (
            await routes.client.put(f"/api/v1/roadmaps/{rid}/favorite", headers=headers(reader2))
        ).status_code == 200
    for order, expected in (("desc", ids), ("asc", list(reversed(ids)))):
        result = await routes.client.get(
            "/api/v1/roadmaps",
            params={"q": keyword, "sortBy": "favoriteCount", "order": order, "pageSize": 2},
        )
        assert result.status_code == 200, result.text
        data = result.json()["data"]
        assert data["total"] == 3
        assert [i["id"] for i in data["items"]] == expected[:2]
        second = await routes.client.get(
            "/api/v1/roadmaps",
            params={
                "q": keyword,
                "sortBy": "favoriteCount",
                "order": order,
                "pageSize": 2,
                "page": 2,
            },
        )
        assert [i["id"] for i in second.json()["data"]["items"]] == expected[2:]
    filtered = await routes.client.get(
        "/api/v1/roadmaps", params={"q": keyword, "difficulty": "advanced"}
    )
    assert [i["id"] for i in filtered.json()["data"]["items"]] == [ids[1]]
    documents[0]["title"] = "UNPUBLISHED_SEARCH_" + first_id
    await save(routes, token, first_id, documents[0])
    for query in ("UNPUBLISHED_SEARCH_" + first_id, "%" + keyword):
        result = await routes.client.get("/api/v1/roadmaps", params={"q": query})
        assert result.json()["data"]["total"] == 0
    for params in ({"page": 0}, {"pageSize": 101}, {"sortBy": "title"}, {"difficulty": "unknown"}):
        assert (await routes.client.get("/api/v1/roadmaps", params=params)).status_code == 422
    for _ in range(2):
        result = await routes.client.delete(
            f"/api/v1/roadmaps/{ids[1]}/favorite", headers=headers(reader2)
        )
        assert result.status_code == 200 and not result.json()["data"]["isFavorited"]
    assert (
        await routes.client.post("/api/v1/auth/logout", headers=headers(reader))
    ).status_code == 200
    assert (
        await routes.client.put(f"/api/v1/roadmaps/{ids[2]}/favorite", headers=headers(reader))
    ).status_code == 401
