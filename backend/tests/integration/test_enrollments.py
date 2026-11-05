"""R05 独立真实 MySQL：并发开始、会话边界、进度、位置及日期事实。"""

import asyncio
import copy
import os
from datetime import datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update

from app.database.models import (
    LearningSession,
    RoadmapCheckin,
    RoadmapFavorite,
    SkillRoadmap,
    UserNodeProgress,
    UserRoadmap,
)
from tests.integration.test_accounts import accounts as accounts  # noqa: F401
from tests.integration.test_accounts import headers
from tests.integration.test_roadmaps import author, graph, publish, save
from tests.integration.test_roadmaps import routes as routes  # noqa: F401

pytestmark = [
    pytest.mark.database,
    pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="需显式独立测试库"),
]


async def setup_learning(routes, optional=False):
    token, rid = await author(routes)
    source = graph()
    if optional:
        source["stages"][1]["nodes"][0].update(isOptional=True, countsTowardProgress=False)
    document = await save(routes, token, rid, source)
    response = await publish(routes, token, rid, document)
    assert response.status_code == 200, response.text
    release = response.json()["data"]["releaseId"]
    name, _ = await routes.register()
    reader = headers(await routes.login(name))
    response = await routes.client.post(
        f"/api/v1/roadmaps/{rid}/enroll", headers=reader, json={"releaseId": release}
    )
    assert response.status_code == 200, response.text
    return token, rid, document, reader, response.json()["data"]


async def get_content(routes, relation, reader):
    response = await routes.client.get(
        f"/api/v1/enrollments/{relation['id']}/content", headers=reader
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def test_r09_privacy_retraction_aggregation_and_independent_subscription(routes):
    """两条路线的日期事实先过滤再聚合，退订、取消关系和隐私收回独立。"""
    owner, rid, doc, reader, relation = await setup_learning(routes)
    viewer_name, viewer_user = await routes.register()
    viewer = headers(await routes.login(viewer_name))
    me = (await routes.client.get("/api/v1/users/me", headers=reader)).json()["data"]
    uid = me["id"]
    base = f"/api/v1/users/{uid}"
    assert (await routes.client.put(base + "/follow", headers=viewer)).status_code == 200
    assert (
        await routes.client.put(f"/api/v1/roadmaps/{rid}/favorite", headers=reader)
    ).status_code == 200
    check = await routes.client.post(
        f"/api/v1/enrollments/{relation['id']}/records",
        headers=reader,
        json={"sessionId": relation["sessionId"]},
    )
    assert check.status_code == 200, check.text
    assert (await routes.client.get(base + "/activities", headers=viewer)).json()["data"][
        "total"
    ] == 0
    assert not (
        await routes.client.get(f"/api/v1/roadmaps/{rid}/subscription", headers=reader)
    ).json()["data"]["subscribed"]
    setting = {
        "publishPublic": True,
        "checkinPublic": True,
        "favoritePublic": True,
        "learningPublic": True,
        "settingsVersion": 1,
    }
    assert (
        await routes.client.patch("/api/v1/users/me/privacy", headers=reader, json=setting)
    ).status_code == 200
    activity = (await routes.client.get(base + "/activities", headers=viewer)).json()["data"]
    assert activity["total"] == 1
    assert {x["activityType"] for x in activity["items"]} == {"checkin"}
    assert "PRIVATE_BODY" not in str(activity) and "sessionId" not in str(activity)
    profile = (await routes.client.get(base + "/profile", headers=viewer)).json()["data"]
    assert profile["favoriteCount"] == profile["learningCount"] == 1
    for category in ("favorite", "learning"):
        assert (
            await routes.client.get(
                base + "/collections", headers=viewer, params={"category": category}
            )
        ).json()["data"]["total"] == 1
    endpoint = f"/api/v1/roadmaps/{rid}/subscription"
    assert (
        await routes.client.put(endpoint, headers=reader, json={"subscribed": True})
    ).status_code == 200
    assert (
        await routes.client.put(endpoint, headers=reader, json={"subscribed": False})
    ).status_code == 200
    assert (
        await routes.client.get(f"/api/v1/enrollments/{relation['id']}", headers=reader)
    ).json()["data"]["status"] == "active"
    await routes.client.delete(f"/api/v1/roadmaps/{rid}/favorite", headers=reader)
    await routes.client.post(
        f"/api/v1/enrollments/{relation['id']}/abandon",
        headers=reader,
        json={"sessionId": relation["sessionId"]},
    )
    assert (await routes.client.get(base + "/activities", headers=viewer)).json()["data"][
        "total"
    ] == 1
    await routes.client.put(f"/api/v1/roadmaps/{rid}/favorite", headers=reader)
    # 重新收藏只生成一个有效新事件，不复活已失效旧事件。
    assert (await routes.client.get(base + "/activities", headers=viewer)).json()["data"][
        "total"
    ] == 1
    setting.update(
        checkinPublic=False, favoritePublic=False, learningPublic=False, settingsVersion=2
    )
    await routes.client.patch("/api/v1/users/me/privacy", headers=reader, json=setting)
    assert (await routes.client.get("/api/v1/users/me/feed", headers=viewer)).json()["data"][
        "total"
    ] == 0
    profile = (await routes.client.get(base + "/profile", headers=viewer)).json()["data"]
    assert profile["favoriteCount"] is None and profile["learningCount"] is None
    assert not profile["canViewFavorites"] and not profile["canViewLearning"]
    setting.update(checkinPublic=True, favoritePublic=True, settingsVersion=3)
    await routes.client.patch("/api/v1/users/me/privacy", headers=reader, json=setting)
    assert (await routes.client.get("/api/v1/users/me/feed", headers=viewer)).json()["data"][
        "total"
    ] == 1
    # 同日第二路线打卡聚合为一条，隐藏后不能泄漏另一条路线的数量或标题。
    rid2 = (
        await routes.client.post(
            "/api/v1/roadmaps", headers=headers(owner), json={"title": "第二路线"}
        )
    ).json()["data"]["id"]
    doc2 = await save(routes, owner, rid2, graph())
    rel2 = (await publish(routes, owner, rid2, doc2)).json()["data"]["releaseId"]
    en2 = (
        await routes.client.post(
            f"/api/v1/roadmaps/{rid2}/enroll", headers=reader, json={"releaseId": rel2}
        )
    ).json()["data"]
    await routes.client.post(
        f"/api/v1/enrollments/{en2['id']}/records",
        headers=reader,
        json={"sessionId": en2["sessionId"]},
    )
    items = (await routes.client.get(base + "/activities", headers=viewer)).json()["data"]["items"]
    day = next(x for x in items if x["activityType"] == "checkin")
    assert day["routeCount"] == 2 and day["roadmapId"] is None
    await routes.client.post(
        f"/api/v1/roadmaps/{rid2}/archive",
        headers=headers(owner),
        json={"expectedVersion": doc2["expectedVersion"]},
    )
    items = (await routes.client.get(base + "/activities", headers=viewer)).json()["data"]["items"]
    day = next(x for x in items if x["activityType"] == "checkin")
    assert day["routeCount"] == 1 and day["roadmapId"] == rid
    # 治理撤销打卡同步收回动态。
    _, admin = await routes.admin()
    res = await routes.client.post(
        f"/api/v1/admin/checkins/{check.json()['data']['id']}/invalidate",
        headers=headers(admin),
        json={"reason": "测试撤销", "expectedValid": True},
    )
    assert res.status_code == 200, res.text
    items = (await routes.client.get(base + "/activities", headers=viewer)).json()["data"]["items"]
    assert all(x["activityType"] != "checkin" for x in items)
    assert (await routes.client.delete(base + "/follow", headers=viewer)).status_code == 200
    assert (await routes.client.get("/api/v1/users/me/feed", headers=viewer)).json()["data"][
        "total"
    ] == 0


async def test_r09_update_prompt_retains_badge_and_discussion_lists(routes):
    """抑制只针对当前目标版本，个人讨论入口不泄漏受限目标。"""
    owner, rid, doc, reader, relation = await setup_learning(routes)
    doc["stages"][0]["nodes"][0]["content"] = "新版内容"
    doc = await save(routes, owner, rid, doc)
    release = (await publish(routes, owner, rid, doc, "新版")).json()["data"]["releaseId"]
    prompt = f"/api/v1/enrollments/{relation['id']}/update-prompt"
    res = await routes.client.put(
        prompt, headers=reader, json={"releaseId": release, "dismissed": True}
    )
    assert res.status_code == 200, res.text
    assert res.json()["data"]["hasNewVersion"] and res.json()["data"]["updatePromptDismissed"]
    assert (
        await routes.client.put(
            prompt, headers=reader, json={"releaseId": relation["releaseId"], "dismissed": True}
        )
    ).status_code == 409
    topic = await routes.client.post(
        f"/api/v1/roadmaps/{rid}/issues",
        headers=reader,
        json={"title": "资源疑问", "body": "我的提问"},
    )
    assert topic.status_code == 201, topic.text
    iid = topic.json()["data"]["id"]
    assert (
        await routes.client.post(
            f"/api/v1/roadmaps/{rid}/issues/{iid}/comments",
            headers=reader,
            json={"body": "我的回复"},
        )
    ).status_code == 201
    for kind in ("questions", "replies"):
        result = await routes.client.get(
            "/api/v1/users/me/discussions", headers=reader, params={"kind": kind}
        )
        assert result.status_code == 200, result.text
        assert result.json()["data"]["total"] == 1
        assert result.json()["data"]["items"][0]["issueId"] == iid
    doc["stages"][0]["nodes"][0]["content"] = "第三版内容"
    doc = await save(routes, owner, rid, doc)
    await publish(routes, owner, rid, doc, "第三版")
    result = (
        await routes.client.get(f"/api/v1/enrollments/{relation['id']}", headers=reader)
    ).json()["data"]
    assert result["hasNewVersion"] and not result["updatePromptDismissed"]


async def test_atomic_concurrent_start_and_private_boundaries(routes):
    owner, rid = await author(routes)
    document = await save(routes, owner, rid, graph())
    release = (await publish(routes, owner, rid, document)).json()["data"]["releaseId"]
    name, _ = await routes.register()
    reader = headers(await routes.login(name))
    endpoint = f"/api/v1/roadmaps/{rid}/enroll"
    assert (await routes.client.post(endpoint, json={"releaseId": release})).status_code == 401
    assert (
        await routes.client.post(endpoint, headers=headers(owner), json={"releaseId": release})
    ).status_code == 403
    # 注入会话插入失败，关系必须与指针一起回滚。
    from sqlalchemy.ext.asyncio import AsyncSession

    original_flush = AsyncSession.flush

    async def failing_flush(session, *args, **kwargs):
        if any(isinstance(row, LearningSession) for row in session.new):
            raise RuntimeError("test-only session failure")
        return await original_flush(session, *args, **kwargs)

    with patch.object(AsyncSession, "flush", failing_flush), pytest.raises(RuntimeError):
        await routes.client.post(endpoint, headers=reader, json={"releaseId": release})
    results = await asyncio.gather(
        *[
            routes.client.post(endpoint, headers=reader, json={"releaseId": release})
            for _ in range(3)
        ]
    )
    assert all(r.status_code == 200 for r in results), [r.text for r in results]
    assert len({r.json()["data"]["sessionId"] for r in results}) == 1
    relation = results[0].json()["data"]
    assert relation["completedNodeCount"] == relation["progressPercent"] == 0
    content = await get_content(routes, relation, reader)
    assert relation["lastNodeId"] == content["stages"][0]["nodes"][0]["id"]
    async with routes.app.state.database.sessions() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(UserRoadmap)
                .where(UserRoadmap.roadmap_id == int(rid))
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(LearningSession)
                .where(LearningSession.roadmap_id == int(rid))
            )
            == 1
        )
        for model, condition in (
            (UserNodeProgress, UserNodeProgress.session_id == int(relation["sessionId"])),
            (RoadmapCheckin, RoadmapCheckin.user_roadmap_id == int(relation["id"])),
            (RoadmapFavorite, RoadmapFavorite.roadmap_id == int(rid)),
        ):
            assert (
                await session.scalar(select(func.count()).select_from(model).where(condition)) == 0
            )
    other_name, _ = await routes.register()
    other = headers(await routes.login(other_name))
    endpoint = f"/api/v1/enrollments/{relation['id']}"
    for suffix in ("", "/content", "/records"):
        assert (await routes.client.get(endpoint + suffix, headers=other)).status_code == 404
    assert (
        "PRIVATE_BODY_V1"
        not in (await routes.client.get(f"/api/v1/roadmaps/{rid}", headers=reader)).text
    )


async def test_position_completion_undo_optional_and_original_version_restore(routes):
    owner, rid, document, reader, relation = await setup_learning(routes, optional=True)
    content = await get_content(routes, relation, reader)
    first = content["stages"][0]["nodes"][0]["id"]
    second = content["stages"][1]["nodes"][0]["id"]
    endpoint = f"/api/v1/enrollments/{relation['id']}"
    payload = {"sessionId": relation["sessionId"]}
    result = await routes.client.patch(
        endpoint + "/position", headers=reader, json={**payload, "nodeId": second}
    )
    assert result.status_code == 200, result.text
    assert result.json()["data"]["lastNodeId"] == second
    assert (await get_content(routes, relation, reader))["progress"] == []
    for completed in (True, True, False, True):
        result = await routes.client.put(
            endpoint + f"/nodes/{first}/status",
            headers=reader,
            json={**payload, "completed": completed},
        )
        assert result.status_code == 200, result.text
        summary = result.json()["data"]
        assert summary["progressPercent"] == (100 if completed else 0)
        assert summary["progressNodeCount"] == 1
    assert summary["completedAt"]
    assert (await routes.client.get(endpoint + "/records", headers=reader)).json()["data"][
        "total"
    ] == 0
    abandoned = await routes.client.post(endpoint + "/abandon", headers=reader, json=payload)
    assert abandoned.json()["data"]["status"] == "abandoned"
    assert (
        await routes.client.patch(
            endpoint + "/position", headers=reader, json={**payload, "nodeId": first}
        )
    ).status_code == 409
    document["title"] = "新版标题"
    document = await save(routes, owner, rid, document)
    newer = (await publish(routes, owner, rid, document, "发布新版")).json()["data"]["releaseId"]
    repeated = (
        await routes.client.post(
            f"/api/v1/roadmaps/{rid}/enroll", headers=reader, json={"releaseId": newer}
        )
    ).json()["data"]
    assert repeated["id"] == relation["id"] and repeated["sessionId"] == relation["sessionId"]
    restored = (
        await routes.client.post(endpoint + "/restore", headers=reader, json=payload)
    ).json()["data"]
    assert restored["releaseId"] == relation["releaseId"] and restored["lastNodeId"] == second
    assert restored["progressPercent"] == 100 and restored["hasNewVersion"]
    # 精确重新登录学习者，验证新登录会话读取原位置。
    from app.database.models import User
    from tests.integration.test_accounts import PASSWORD

    async with routes.app.state.database.sessions() as session:
        reader_name = await session.scalar(
            select(User.username)
            .join(UserRoadmap, UserRoadmap.user_id == User.id)
            .where(UserRoadmap.id == int(relation["id"]))
        )

    login = await routes.client.post(
        "/api/v1/auth/login",
        json={"username": reader_name, "password": PASSWORD},
    )
    assert login.status_code == 200
    reader = headers(login.json()["data"]["accessToken"])
    assert (await get_content(routes, relation, reader))["enrollment"]["lastNodeId"] == second
    listing = (await routes.client.get("/api/v1/users/me/enrollments", headers=reader)).json()[
        "data"
    ]
    assert listing["total"] == 1
    await routes.client.post(
        f"/api/v1/roadmaps/{rid}/archive",
        headers=headers(owner),
        json={"expectedVersion": document["expectedVersion"]},
    )
    assert (await get_content(routes, relation, reader))["enrollment"]["contentAvailable"]


async def test_session_and_release_node_rejection_and_platform_restrictions(routes):
    _, rid, _, reader, relation = await setup_learning(routes)
    content = await get_content(routes, relation, reader)
    node = content["stages"][0]["nodes"][0]["id"]
    endpoint = f"/api/v1/enrollments/{relation['id']}"
    stale = {"sessionId": str(int(relation["sessionId"]) + 99999)}
    for suffix, method, payload in (
        ("/position", "patch", {**stale, "nodeId": node}),
        (f"/nodes/{node}/status", "put", {**stale, "completed": True}),
        ("/records", "post", stale),
        ("/restore", "post", stale),
    ):
        assert (
            await getattr(routes.client, method)(endpoint + suffix, headers=reader, json=payload)
        ).status_code == 409
    payload = {"sessionId": relation["sessionId"]}
    assert (
        await routes.client.patch(
            endpoint + "/position", headers=reader, json={**payload, "nodeId": "999999999"}
        )
    ).status_code == 404
    assert (
        await routes.client.put(
            endpoint + f"/nodes/{node}/status", headers=reader, json={"status": "completed"}
        )
    ).status_code == 422
    async with routes.app.state.database.sessions() as session, session.begin():
        await session.execute(
            update(SkillRoadmap)
            .where(SkillRoadmap.id == int(rid))
            .values(moderation_status="disabled")
        )
    assert (await routes.client.get(endpoint + "/content", headers=reader)).status_code == 409
    assert (
        await routes.client.post(endpoint + "/records", headers=reader, json=payload)
    ).status_code == 409
    assert (
        await routes.client.post(endpoint + "/abandon", headers=reader, json=payload)
    ).status_code == 200
    assert (
        await routes.client.post(endpoint + "/restore", headers=reader, json=payload)
    ).status_code == 409
    summary = (await routes.client.get(endpoint, headers=reader)).json()["data"]
    assert summary["title"] == "内容已下架" and summary["nodeCount"] == 0


async def test_beijing_midnight_concurrent_checkins_and_valid_day_statistics(routes):
    _, _, _, reader, relation = await setup_learning(routes)
    endpoint = f"/api/v1/enrollments/{relation['id']}/records"
    payload = {"sessionId": relation["sessionId"]}
    with patch(
        "app.services.enrollment_service.now", return_value=datetime(2026, 10, 31, 15, 59, 59)
    ):
        results = await asyncio.gather(
            *[routes.client.post(endpoint, headers=reader, json=payload) for _ in range(3)]
        )
    assert all(r.status_code == 200 for r in results), [r.text for r in results]
    assert len({r.json()["data"]["id"] for r in results}) == 1
    assert results[0].json()["data"]["checkinDate"] == "2026-10-31"
    with patch("app.services.enrollment_service.now", return_value=datetime(2026, 10, 31, 16)):
        assert (await routes.client.post(endpoint, headers=reader, json=payload)).json()["data"][
            "checkinDate"
        ] == "2026-11-01"
        overview = (
            await routes.client.get(
                "/api/v1/users/me/learning-overview?month=2026-11", headers=reader
            )
        ).json()["data"]
        assert (
            overview["checkinDayCount"]
            == overview["currentStreak"]
            == overview["longestStreak"]
            == 2
        )
        assert overview["calendarDates"] == ["2026-11-01"]
    async with routes.app.state.database.sessions() as session, session.begin():
        record = await session.scalar(
            select(RoadmapCheckin)
            .where(RoadmapCheckin.user_roadmap_id == int(relation["id"]))
            .order_by(RoadmapCheckin.id.desc())
        )
        record.is_valid = 0
        record.invalidated_at = datetime(2026, 11, 1)
        from app.database.models import User

        record.invalidated_by = await session.scalar(
            select(User.id).where(User.username.in_(routes.names)).limit(1)
        )
    with patch("app.services.enrollment_service.now", return_value=datetime(2026, 10, 31, 16)):
        assert not (await routes.client.post(endpoint, headers=reader, json=payload)).json()[
            "data"
        ]["isValid"]
        overview = (
            await routes.client.get("/api/v1/users/me/learning-overview", headers=reader)
        ).json()["data"]
        assert overview["checkinDayCount"] == 1
    for old in (
        {"sessionId": relation["sessionId"], "content": "旧收获"},
        {"sessionId": relation["sessionId"], "checkinDate": "2026-01-01"},
    ):
        assert (await routes.client.post(endpoint, headers=reader, json=old)).status_code == 422


async def test_three_routes_same_day_count_once_and_remain_private(routes):
    first = await setup_learning(routes)
    reader = first[3]
    relations = [first[4]]
    for _ in range(2):
        _, rid, _, _, other_relation = await setup_learning(routes)
        response = await routes.client.post(
            f"/api/v1/roadmaps/{rid}/enroll",
            headers=reader,
            json={"releaseId": other_relation["releaseId"]},
        )
        assert response.status_code == 200, response.text
        relations.append(response.json()["data"])
    for relation in relations:
        response = await routes.client.post(
            f"/api/v1/enrollments/{relation['id']}/records",
            headers=reader,
            json={"sessionId": relation["sessionId"]},
        )
        assert response.status_code == 200, response.text
    overview = (
        await routes.client.get("/api/v1/users/me/learning-overview", headers=reader)
    ).json()["data"]
    assert overview["checkinDayCount"] == overview["currentStreak"] == 1
    assert len(overview["calendarDates"]) == 1
    outsider, _ = await routes.register()
    other = headers(await routes.login(outsider))
    overview = (
        await routes.client.get("/api/v1/users/me/learning-overview", headers=other)
    ).json()["data"]
    assert overview["checkinDayCount"] == overview["learningRoadmapCount"] == 0


async def test_real_previous_session_and_cross_version_nodes_cannot_write(routes):
    owner, rid, document, reader, relation = await setup_learning(routes)
    old_node = (await get_content(routes, relation, reader))["stages"][0]["nodes"][0]["id"]
    document["title"] = "新版会话测试"
    document = await save(routes, owner, rid, document)
    release = (await publish(routes, owner, rid, document, "新版本")).json()["data"]["releaseId"]
    # R06 尚未开放升级接口，只在精确测试夹具内模拟已切换当前会话。
    async with routes.app.state.database.sessions() as session, session.begin():
        learning = LearningSession(
            user_roadmap_id=int(relation["id"]),
            roadmap_id=int(rid),
            release_id=int(release),
            source_session_id=int(relation["sessionId"]),
            progress_version=1,
            started_at=datetime(2026, 11, 2),
        )
        session.add(learning)
        await session.flush()
        new_id = learning.id
        await session.execute(
            update(UserRoadmap)
            .where(UserRoadmap.id == int(relation["id"]))
            .values(current_session_id=new_id)
        )
    endpoint = f"/api/v1/enrollments/{relation['id']}"
    assert (
        await routes.client.post(
            endpoint + "/records", headers=reader, json={"sessionId": relation["sessionId"]}
        )
    ).status_code == 409
    assert (
        await routes.client.put(
            endpoint + f"/nodes/{old_node}/status",
            headers=reader,
            json={"sessionId": str(new_id), "completed": True},
        )
    ).status_code == 404
    assert (await get_content(routes, relation, reader))["enrollment"]["releaseId"] == release


async def test_concurrent_completion_uses_current_progress_after_lock_wait(routes):
    _, _, _, reader, relation = await setup_learning(routes)
    content = await get_content(routes, relation, reader)
    nodes = [n["id"] for stage in content["stages"] for n in stage["nodes"]]
    endpoint = f"/api/v1/enrollments/{relation['id']}"
    results = await asyncio.gather(
        *[
            routes.client.put(
                endpoint + f"/nodes/{node}/status",
                headers=reader,
                json={"sessionId": relation["sessionId"], "completed": True},
            )
            for node in nodes
        ]
    )
    assert all(response.status_code == 200 for response in results)
    assert max(response.json()["data"]["progressPercent"] for response in results) == 100
    summary = (await routes.client.get(endpoint, headers=reader)).json()["data"]
    assert summary["progressPercent"] == 100 and summary["completedAt"] is not None


async def version_preview(routes, relation, reader):
    response = await routes.client.get(
        f"/api/v1/enrollments/{relation['id']}/upgrade/preview", headers=reader
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def upgrade_payload(preview, confirmations=None):
    return {
        "sourceSessionId": preview["sourceSessionId"],
        "targetReleaseId": preview["targetReleaseId"],
        "progressVersion": preview["progressVersion"],
        "requestKey": str(uuid4()),
        "confirmations": confirmations or [],
    }


async def complete_node(routes, relation, reader, node_id):
    response = await routes.client.put(
        f"/api/v1/enrollments/{relation['id']}/nodes/{node_id}/status",
        headers=reader,
        json={"sessionId": relation["sessionId"], "completed": True},
    )
    assert response.status_code == 200, response.text


async def next_version(routes, owner, rid, document):
    document = await save(routes, owner, rid, document)
    response = await publish(routes, owner, rid, document, "更新学习任务")
    assert response.status_code == 200, response.text
    return document, response.json()["data"]["releaseId"]


async def test_upgrade_preview_retains_identity_and_changes_progress_denominator(routes):
    owner, rid, document, reader, relation = await setup_learning(routes)
    source = await get_content(routes, relation, reader)
    first, second = [s["nodes"][0] for s in source["stages"]]
    await complete_node(routes, relation, reader, first["id"])
    await routes.client.patch(
        f"/api/v1/enrollments/{relation['id']}/position",
        headers=reader,
        json={"sessionId": relation["sessionId"], "nodeId": second["id"]},
    )
    replacement = copy.deepcopy(document["stages"][1]["nodes"][0])
    replacement.update(id="tmp_replacement", stableKey=None, revisionNo=None, title="新增主线")
    replacement["resources"][0]["id"] = "tmp_replacement_resource"
    document["stages"][1]["nodes"] = [replacement]
    kept = document["stages"][0]["nodes"][0]
    kept["title"] = "改名仍是同一目标"
    kept["resources"][0]["resourceUrl"] = "https://example.com/retain-resource"
    document, _ = await next_version(routes, owner, rid, document)
    preview = await version_preview(routes, relation, reader)
    changes = preview["nodeChanges"]
    retained = next(row for row in changes if "renamed" in row["changes"])
    assert "resources" in retained["changes"] and not retained["requiresConfirmation"]
    assert any("added" in row["changes"] for row in changes)
    assert any("removed" in row["changes"] for row in changes)
    before = (await get_content(routes, relation, reader))["enrollment"]
    assert before["sessionId"] == relation["sessionId"] and before["progressPercent"] == 50
    response = await routes.client.post(
        f"/api/v1/enrollments/{relation['id']}/upgrade",
        headers=reader,
        json=upgrade_payload(preview),
    )
    assert response.status_code == 200, response.text
    receipt = response.json()["data"]
    target = await get_content(routes, relation, reader)
    assert receipt["targetSessionId"] != relation["sessionId"]
    assert target["enrollment"]["progressPercent"] == 50
    assert target["enrollment"]["lastNodeId"] == target["stages"][1]["nodes"][0]["id"]
    historical = await routes.client.get(
        f"/api/v1/enrollments/{relation['id']}/content?sessionId={relation['sessionId']}",
        headers=reader,
    )
    assert historical.status_code == 200
    old = historical.json()["data"]
    assert old["enrollment"]["writable"] is False and old["enrollment"]["isCurrentSession"] is False
    assert old["stages"][0]["nodes"][0]["title"] == first["title"]
    assert old["enrollment"]["progressPercent"] == 50
    history = (
        await routes.client.get(f"/api/v1/enrollments/{relation['id']}/sessions", headers=reader)
    ).json()["data"]
    assert history["total"] == 2 and sum(row["isCurrentSession"] for row in history["items"]) == 1


@pytest.mark.parametrize("action,expected", [("keep", 1), ("relearn", 0)])
async def test_v1_direct_to_v3_requires_semantic_choice_even_when_latest_policy_retains(
    routes, action, expected
):
    owner, rid, document, reader, relation = await setup_learning(routes)
    first = (await get_content(routes, relation, reader))["stages"][0]["nodes"][0]
    await complete_node(routes, relation, reader, first["id"])
    document["stages"][0]["nodes"][0].update(content="新学习要求", changePolicy="reconfirm")
    document, _ = await next_version(routes, owner, rid, document)
    document["stages"][0]["nodes"][0]["changePolicy"] = "retain"
    document["title"] = "第三版本"
    document, _ = await next_version(routes, owner, rid, document)
    preview = await version_preview(routes, relation, reader)
    required = [row for row in preview["nodeChanges"] if row["requiresConfirmation"]]
    assert len(required) == 1 and preview["targetVersionNo"] == 3
    assert required[0]["sourceExcerpt"] == "PRIVATE_BODY_V1"
    assert required[0]["targetExcerpt"] == "新学习要求"
    assert preview["completedMin"] == 0 and preview["completedMax"] == 1
    endpoint = f"/api/v1/enrollments/{relation['id']}/upgrade"
    assert (
        await routes.client.post(endpoint, headers=reader, json=upgrade_payload(preview))
    ).status_code == 422
    payload = upgrade_payload(preview, [{"stableKey": required[0]["stableKey"], "action": action}])
    response = await routes.client.post(endpoint, headers=reader, json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["completedNodeCount"] == expected
    # 所有旧标签页写操作均不能写到升级后的当前会话。
    for method, suffix, data in (
        ("put", f"/nodes/{first['id']}/status", {"completed": True}),
        ("patch", "/position", {"nodeId": first["id"]}),
        ("post", "/records", {}),
    ):
        result = await getattr(routes.client, method)(
            f"/api/v1/enrollments/{relation['id']}" + suffix,
            headers=reader,
            json={"sessionId": relation["sessionId"], **data},
        )
        assert result.status_code == 409


async def test_upgrade_rejects_expired_preview_and_replays_same_receipt(
    routes,
):
    owner, rid, document, reader, relation = await setup_learning(routes)
    source = await get_content(routes, relation, reader)
    first, second = [s["nodes"][0]["id"] for s in source["stages"]]
    document["title"] = "第二版"
    document, _ = await next_version(routes, owner, rid, document)
    endpoint = f"/api/v1/enrollments/{relation['id']}/upgrade"
    payload = upgrade_payload(await version_preview(routes, relation, reader))
    await complete_node(routes, relation, reader, first)
    assert (await routes.client.post(endpoint, headers=reader, json=payload)).status_code == 409
    payload = upgrade_payload(await version_preview(routes, relation, reader))
    await routes.client.patch(
        f"/api/v1/enrollments/{relation['id']}/position",
        headers=reader,
        json={"sessionId": relation["sessionId"], "nodeId": second},
    )
    assert (await routes.client.post(endpoint, headers=reader, json=payload)).status_code == 409
    payload = upgrade_payload(await version_preview(routes, relation, reader))
    document["title"] = "第三版"
    document, _ = await next_version(routes, owner, rid, document)
    assert (await routes.client.post(endpoint, headers=reader, json=payload)).status_code == 409
    payload = upgrade_payload(await version_preview(routes, relation, reader))
    responses = await asyncio.gather(
        *[routes.client.post(endpoint, headers=reader, json=payload) for _ in range(3)]
    )
    assert all(response.status_code == 200 for response in responses), [r.text for r in responses]
    receipt = responses[0].json()["data"]
    assert all(response.json()["data"] == receipt for response in responses)
    conflicting = await routes.client.post(
        endpoint,
        headers=reader,
        json={**payload, "progressVersion": payload["progressVersion"] + 1},
    )
    assert (
        conflicting.status_code == 409
        and conflicting.json()["data"]["errorCode"] == "UPGRADE_REQUEST_CONFLICT"
    )
    assert (
        await routes.client.post(
            endpoint, headers=reader, json={**payload, "requestKey": str(uuid4())}
        )
    ).status_code == 409
    document["title"] = "第四版"
    await next_version(routes, owner, rid, document)
    assert (await routes.client.post(endpoint, headers=reader, json=payload)).json()[
        "data"
    ] == receipt


async def test_upgrade_failure_rolls_back_session_progress_event_and_pointer_with_today_checkin(
    routes,
):
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.database.models import LearningSessionEvent

    owner, rid, document, reader, relation = await setup_learning(routes)
    first = (await get_content(routes, relation, reader))["stages"][0]["nodes"][0]["id"]
    await complete_node(routes, relation, reader, first)
    await routes.client.post(
        f"/api/v1/enrollments/{relation['id']}/records",
        headers=reader,
        json={"sessionId": relation["sessionId"]},
    )
    document["title"] = "第二版"
    await next_version(routes, owner, rid, document)
    payload = upgrade_payload(await version_preview(routes, relation, reader))
    original = AsyncSession.flush

    async def fail_at_event(session, *args, **kwargs):
        if any(
            isinstance(row, LearningSessionEvent) and row.event_type == "upgrade"
            for row in session.new
        ):
            raise RuntimeError("test-only upgrade rollback")
        return await original(session, *args, **kwargs)

    endpoint = f"/api/v1/enrollments/{relation['id']}/upgrade"
    with patch.object(AsyncSession, "flush", fail_at_event), pytest.raises(RuntimeError):
        await routes.client.post(endpoint, headers=reader, json=payload)
    async with routes.app.state.database.sessions() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(LearningSession)
                .where(LearningSession.roadmap_id == int(rid))
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(LearningSessionEvent)
                .where(
                    LearningSessionEvent.user_roadmap_id == int(relation["id"]),
                    LearningSessionEvent.event_type == "upgrade",
                )
            )
            == 0
        )
    source = await get_content(routes, relation, reader)
    assert (
        source["enrollment"]["sessionId"] == relation["sessionId"]
        and source["enrollment"]["completedNodeCount"] == 1
    )
    result = await routes.client.post(endpoint, headers=reader, json=payload)
    assert result.status_code == 200, result.text
    assert (
        await routes.client.get(f"/api/v1/enrollments/{relation['id']}/records", headers=reader)
    ).json()["data"]["total"] == 1
    target_id = result.json()["data"]["targetSessionId"]
    repeat = await routes.client.post(
        f"/api/v1/enrollments/{relation['id']}/records",
        headers=reader,
        json={"sessionId": target_id},
    )
    assert repeat.status_code == 200
    assert repeat.json()["data"]["sessionId"] == relation["sessionId"]


async def test_deleted_node_restored_later_does_not_recover_ancient_completion(routes):
    owner, rid, document, reader, relation = await setup_learning(routes)
    original_node = copy.deepcopy(document["stages"][0]["nodes"][0])
    first = (await get_content(routes, relation, reader))["stages"][0]["nodes"][0]["id"]
    await complete_node(routes, relation, reader, first)
    replacement = copy.deepcopy(original_node)
    replacement.update(id="tmp_new_goal", stableKey=None, revisionNo=None, title="另一个任务")
    replacement["resources"][0]["id"] = "tmp_new_resource"
    document["stages"][0]["nodes"] = [replacement]
    document, _ = await next_version(routes, owner, rid, document)
    endpoint = f"/api/v1/enrollments/{relation['id']}/upgrade"
    response = await routes.client.post(
        endpoint,
        headers=reader,
        json=upgrade_payload(await version_preview(routes, relation, reader)),
    )
    assert response.status_code == 200, response.text
    # 草稿资源删除后不复用旧资源ID；任务节点的稳定身份仍按原节点恢复。
    original_node["resources"][0]["id"] = "tmp_restored_resource"
    document["stages"][0]["nodes"].append(original_node)
    document, _ = await next_version(routes, owner, rid, document)
    preview = await version_preview(routes, relation, reader)
    restored = next(
        row for row in preview["nodeChanges"] if row["stableKey"] == original_node["stableKey"]
    )
    assert restored["changes"] == ["added"] and not restored["isCompleted"]
    response = await routes.client.post(endpoint, headers=reader, json=upgrade_payload(preview))
    assert response.status_code == 200, response.text
    assert response.json()["data"]["completedNodeCount"] == 0
    historical = (
        await routes.client.get(
            f"/api/v1/enrollments/{relation['id']}/content?sessionId={relation['sessionId']}",
            headers=reader,
        )
    ).json()["data"]
    assert historical["enrollment"]["completedNodeCount"] == 1


async def test_twenty_node_source_stays_ten_of_twenty_until_confirmed_upgrade(routes):
    owner, rid = await author(routes)
    source = graph()
    base = source["stages"][0]["nodes"][0]
    source["stages"] = [source["stages"][0]]
    source["connections"] = []
    source["stages"][0]["nodes"] = []
    for i in range(20):
        node = copy.deepcopy(base)
        node.update(id=f"tmp_node_{i}", title=f"任务{i}")
        node["resources"][0]["id"] = f"tmp_resource_{i}"
        source["stages"][0]["nodes"].append(node)
    document = await save(routes, owner, rid, source)
    release = (await publish(routes, owner, rid, document)).json()["data"]["releaseId"]
    name, _ = await routes.register()
    reader = headers(await routes.login(name))
    relation = (
        await routes.client.post(
            f"/api/v1/roadmaps/{rid}/enroll", headers=reader, json={"releaseId": release}
        )
    ).json()["data"]
    original = await get_content(routes, relation, reader)
    for node in original["stages"][0]["nodes"][:10]:
        await complete_node(routes, relation, reader, node["id"])
    added = copy.deepcopy(base)
    added.update(id="tmp_extra", title="额外任务")
    added["resources"][0]["id"] = "tmp_extra_resource"
    document["stages"][0]["nodes"].append(added)
    document, _ = await next_version(routes, owner, rid, document)
    preview = await version_preview(routes, relation, reader)
    assert (preview["sourceCompleted"], preview["sourceTotal"], preview["targetTotal"]) == (
        10,
        20,
        21,
    )
    before = (await get_content(routes, relation, reader))["enrollment"]
    assert (
        before["completedNodeCount"],
        before["progressNodeCount"],
        before["progressPercent"],
    ) == (10, 20, 50)
    response = await routes.client.post(
        f"/api/v1/enrollments/{relation['id']}/upgrade",
        headers=reader,
        json=upgrade_payload(preview),
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["progressPercent"] == 47


async def test_upgrade_private_history_and_governance_boundaries(routes):
    from app.database.models import RoadmapRelease, User

    owner, rid, document, reader, relation = await setup_learning(routes)
    document["title"] = "新版本权限验证"
    document, release_id = await next_version(routes, owner, rid, document)
    endpoint = f"/api/v1/enrollments/{relation['id']}"
    payload = upgrade_payload(await version_preview(routes, relation, reader))
    assert (await routes.client.get(endpoint + "/upgrade/preview")).status_code == 401
    _, admin = await routes.admin()
    for credential, forbidden in ((headers(owner), 404), (headers(admin), 403)):
        assert (
            await routes.client.get(endpoint + "/upgrade/preview", headers=credential)
        ).status_code == forbidden
        assert (
            await routes.client.get(endpoint + "/sessions", headers=credential)
        ).status_code == forbidden
        assert (
            await routes.client.get(
                endpoint + f"/content?sessionId={relation['sessionId']}", headers=credential
            )
        ).status_code == forbidden
        assert (
            await routes.client.post(endpoint + "/upgrade", headers=credential, json=payload)
        ).status_code == forbidden
    assert (
        await routes.client.get(endpoint + "/content?sessionId=999999999", headers=reader)
    ).status_code == 404
    await routes.client.post(
        endpoint + "/abandon", headers=reader, json={"sessionId": relation["sessionId"]}
    )
    assert (
        await routes.client.post(endpoint + "/upgrade", headers=reader, json=payload)
    ).status_code == 409
    await routes.client.post(
        endpoint + "/restore", headers=reader, json={"sessionId": relation["sessionId"]}
    )
    for mode in ("archive", "moderated", "restricted", "author_disabled"):
        async with routes.app.state.database.sessions() as session, session.begin():
            route = await session.get(SkillRoadmap, int(rid))
            release = await session.get(RoadmapRelease, int(release_id))
            author_user = await session.get(User, route.creator_id)
            route.distribution_status = "archived" if mode == "archive" else "published"
            route.moderation_status = "disabled" if mode == "moderated" else "normal"
            release.content_access = "restricted" if mode == "restricted" else "normal"
            author_user.status = "disabled" if mode == "author_disabled" else "active"
        assert (
            await routes.client.get(endpoint + "/upgrade/preview", headers=reader)
        ).status_code == 409
        assert (
            await routes.client.post(endpoint + "/upgrade", headers=reader, json=payload)
        ).status_code == 409
