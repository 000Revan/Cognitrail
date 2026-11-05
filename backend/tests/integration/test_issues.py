"""R07真实MySQL：话题闭环、授权、并发、事务及通知恢复。"""

import asyncio
import os
from datetime import timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    IssueSubscription,
    Notification,
    NotificationOutbox,
    RoadmapSubscription,
    SkillRoadmap,
    User,
    UserPrivacySettings,
    UserRoadmap,
)
from app.services.issue_service import now
from app.services.notification_service import OutboxDispatcher
from tests.integration.test_accounts import accounts as accounts  # noqa: F401
from tests.integration.test_accounts import headers
from tests.integration.test_roadmaps import author, graph, publish, save
from tests.integration.test_roadmaps import routes as routes  # noqa: F401

pytestmark = [
    pytest.mark.database,
    pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="需显式独立测试库"),
]


async def setup(routes):
    token, rid = await author(routes)
    doc = await save(routes, token, rid, graph())
    assert (await publish(routes, token, rid, doc)).status_code == 200
    name, user = await routes.register()
    reader = headers(await routes.login(name))
    endpoint = f"/api/v1/roadmaps/{rid}/issues"
    result = await routes.client.post(
        endpoint, headers=reader, json={"title": "视频失效", "body": "第三阶段视频无法打开"}
    )
    assert result.status_code == 201, result.text
    return headers(token), reader, rid, endpoint, result.json()["data"], user


async def drain(routes):
    dispatcher = OutboxDispatcher(routes.app.state.database, routes.app.state.settings)
    for _ in range(100):
        if not await dispatcher.run_once():
            return
    pytest.fail("outbox未排空")


async def test_profile_topic_privacy_is_independent_and_retracts_hidden_targets(routes):
    owner, reader, rid, base, issue, user = await setup(routes)
    endpoint = f"/api/v1/users/{user['id']}/activities"
    assert (await routes.client.get(endpoint, headers=owner)).json()["data"]["total"] == 0
    assert (await routes.client.get(endpoint, headers=reader)).json()["data"]["total"] == 1
    setting = (await routes.client.get("/api/v1/users/me/privacy", headers=reader)).json()["data"]
    assert setting["topicPublic"] is False
    setting.update(topicPublic=True, publishPublic=False)
    result = await routes.client.patch("/api/v1/users/me/privacy", headers=reader, json=setting)
    assert result.status_code == 200, result.text
    legacy = {key: value for key, value in result.json()["data"].items() if key != "topicPublic"}
    retained = await routes.client.patch("/api/v1/users/me/privacy", headers=reader, json=legacy)
    assert retained.status_code == 200 and retained.json()["data"]["topicPublic"] is True
    items = (await routes.client.get(endpoint, headers=owner)).json()["data"]["items"]
    assert (
        len(items) == 1
        and items[0]["activityType"] == "topic"
        and items[0]["issueId"] == issue["id"]
    )
    assert "body" not in items[0] and "第三阶段视频无法打开" not in str(items)
    await routes.client.post(
        base + "/" + issue["id"] + "/comments", headers=reader, json={"body": "不展示的回复"}
    )
    assert (await routes.client.get(endpoint, headers=owner)).json()["data"]["total"] == 1
    setting = result.json()["data"]
    setting["topicPublic"] = False
    result = await routes.client.patch("/api/v1/users/me/privacy", headers=reader, json=setting)
    assert (await routes.client.get(endpoint, headers=owner)).json()["data"]["total"] == 0
    setting = result.json()["data"]
    setting["topicPublic"] = True
    await routes.client.patch("/api/v1/users/me/privacy", headers=reader, json=setting)
    assert (await routes.client.get(endpoint, headers=owner)).json()["data"]["total"] == 1
    await routes.client.delete(base + "/" + issue["id"], headers=reader)
    assert (await routes.client.get(endpoint, headers=owner)).json()["data"]["total"] == 0


async def test_only_creator_can_handle_topics_and_list_stats_sort(routes):
    owner, reader, rid, base, issue, _ = await setup(routes)
    url = base + "/" + issue["id"]
    assert not (await routes.client.get(url, headers=reader)).json()["data"]["canResolve"]
    assert (
        await routes.client.patch(
            url + "/state", headers=reader, json={"status": "resolved", "expectedStatus": "open"}
        )
    ).status_code == 403
    second = (
        await routes.client.post(
            base, headers=reader, json={"title": "第二个话题", "body": "请教另一个问题"}
        )
    ).json()["data"]
    assert (
        await routes.client.patch(
            url + "/state",
            headers=owner,
            json={"status": "closed", "expectedStatus": "open", "reason": "重复"},
        )
    ).status_code == 200
    listing = (
        await routes.client.get(base + "?sortBy=createdAt&order=asc", headers=reader)
    ).json()["data"]
    assert listing["topicCount"] == 2 and listing["closedCount"] == 1
    assert [x["id"] for x in listing["items"]] == [issue["id"], second["id"]]
    assert (await routes.client.get(base + "?status=open", headers=reader)).json()["data"][
        "total"
    ] == 1


async def test_grouped_thread_replies_anchor_and_deleted_root(routes):
    owner, reader, rid, base, issue, user = await setup(routes)
    url = base + "/" + issue["id"]

    third_name, third_user = await routes.register()
    third = headers(await routes.login(third_name))

    async def post(body, parent=None, actor=None):
        r = await routes.client.post(
            url + "/comments",
            headers=actor or reader,
            json={"body": body, "replyToCommentId": parent},
        )
        assert r.status_code == 201, r.text
        return r.json()["data"]["commentId"]

    root = await post("主评论", actor=owner)
    child = await post("回复主评论", root)
    grandchild = await post("继续回复", child, third)
    other = await post("另一个主评论")
    grouped = (await routes.client.get(url + "?commentId=" + grandchild, headers=owner)).json()[
        "data"
    ]
    assert grouped["commentCount"] == 4 and grouped["comments"]["total"] == 2
    thread = grouped["comments"]["items"][0]
    assert thread["id"] == root
    assert [r["id"] for r in thread["replies"]["items"]] == [child, grandchild]
    assert thread["replies"]["items"][1]["replyToAuthor"]["id"] == user["id"]
    assert thread["replies"]["items"][1]["author"]["id"] == third_user["id"]
    assert "avatarUrl" in thread["author"]
    assert (await routes.client.delete(url + "/comments/" + root, headers=owner)).status_code == 200
    thread = (await routes.client.get(url, headers=owner)).json()["data"]["comments"]["items"][0]
    assert thread["body"] is None and thread["replies"]["total"] == 2
    assert (
        await routes.client.delete(url + "/comments/" + child, headers=reader)
    ).status_code == 200
    grouped = (await routes.client.get(url + "?commentId=" + grandchild, headers=owner)).json()[
        "data"
    ]
    assert grouped["commentCount"] == 2
    assert [r["id"] for r in grouped["comments"]["items"][0]["replies"]["items"]] == [grandchild]
    assert (
        await routes.client.delete(url + "/comments/" + grandchild, headers=third)
    ).status_code == 200
    grouped = (await routes.client.get(url, headers=owner)).json()["data"]
    assert grouped["comments"]["total"] == 1 and grouped["commentCount"] == 1
    assert grouped["comments"]["items"][0]["id"] == other
    assert (await routes.client.get(url + "?commentId=" + child, headers=owner)).status_code == 404
    last_page = (await routes.client.get(url + "?page=2", headers=owner)).json()["data"]
    assert last_page["comments"]["page"] == 1
    assert last_page["comments"]["items"][0]["id"] == other


async def test_discussion_profile_is_login_only_public_and_privacy_filtered(routes):
    owner, reader, rid, base, issue, _ = await setup(routes)
    async with routes.app.state.database.sessions() as s:
        creator_id = await s.scalar(
            select(SkillRoadmap.creator_id).where(SkillRoadmap.id == int(rid))
        )
    endpoint = f"/api/v1/users/{creator_id}/profile"
    assert (await routes.client.get(endpoint)).status_code == 401
    response = await routes.client.get(endpoint, headers=reader)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["roadmaps"]["total"] == 1 and data["roadmaps"]["items"][0]["id"] == rid
    assert (
        not {"passwordHash", "learning", "enrollments", "privacy", "checkins", "lastLoginAt"}
        & data.keys()
    )
    async with routes.app.state.database.sessions() as s, s.begin():
        await s.execute(
            update(UserPrivacySettings)
            .where(UserPrivacySettings.user_id == creator_id)
            .values(publish_public=0)
        )
    assert (await routes.client.get(endpoint, headers=reader)).json()["data"]["roadmaps"][
        "total"
    ] == 1
    async with routes.app.state.database.sessions() as s, s.begin():
        await s.execute(update(User).where(User.id == creator_id).values(status="disabled"))
    assert (await routes.client.get(endpoint, headers=reader)).status_code == 404


async def test_author_self_subscription_rate_limits_and_duplicate_body(routes):
    owner, reader, rid, base, issue, _ = await setup(routes)
    url = base + "/" + issue["id"]
    duplicate = await routes.client.post(
        base, headers=reader, json={"title": "视频失效", "body": "第三阶段视频无法打开"}
    )
    assert duplicate.status_code == 409
    created = await routes.client.post(
        base, headers=owner, json={"title": "作者说明", "body": "维护说明"}
    )
    own_issue = created.json()["data"]["id"]
    await drain(routes)
    async with routes.app.state.database.sessions() as s:
        assert (
            await s.scalar(
                select(func.count())
                .select_from(IssueSubscription)
                .where(IssueSubscription.issue_id == int(own_issue))
            )
            == 1
        )
        assert (
            await s.scalar(
                select(func.count())
                .select_from(Notification)
                .where(Notification.issue_id == int(own_issue))
            )
            == 0
        )
    routes.app.state.discussion_user_limiter.limit = 1
    assert (
        await routes.client.post(url + "/comments", headers=reader, json={"body": "超用户限额"})
    ).status_code == 429
    routes.app.state.discussion_user_limiter.limit = 1000
    routes.app.state.discussion_ip_limiter.limit = 1
    assert (
        await routes.client.post(url + "/comments", headers=reader, json={"body": "超IP限额"})
    ).status_code == 429


async def test_anchor_pagination_concurrent_claims_and_failed_retry_limit(routes):
    owner, reader, rid, base, issue, _ = await setup(routes)
    routes.app.state.discussion_user_limiter.limit = 1000
    url = base + "/" + issue["id"]
    last = None
    for i in range(22):
        result = await routes.client.post(
            url + "/comments", headers=owner, json={"body": f"回复{i}"}
        )
        assert result.status_code == 201, result.text
        last = result.json()["data"]["commentId"]
    result = (await routes.client.get(url + "?commentId=" + last, headers=reader)).json()["data"]
    assert result["comments"]["page"] == 2 and len(result["comments"]["items"]) == 2
    anchor = None
    for i in range(7):
        response = await routes.client.post(
            url + "/comments", headers=reader, json={"body": f"楼中楼{i}", "replyToCommentId": last}
        )
        assert response.status_code == 201, response.text
        anchor = response.json()["data"]["commentId"]
    result = (await routes.client.get(url + "?commentId=" + anchor, headers=reader)).json()["data"]
    thread = result["comments"]["items"][-1]
    assert result["comments"]["page"] == 2 and thread["id"] == last
    assert thread["replies"]["page"] == 2 and len(thread["replies"]["items"]) == 2
    replies = (
        await routes.client.get(url + "/comments/" + last + "/replies", headers=reader)
    ).json()["data"]
    assert replies["total"] == 7 and len(replies["items"]) == 5
    dispatcher = OutboxDispatcher(
        routes.app.state.database,
        routes.app.state.settings.model_copy(update={"outbox_max_attempts": 1}),
    )
    claims = await asyncio.gather(*(dispatcher.claim() for _ in range(3)))
    assert len({task[0] for task in claims}) == 3
    await dispatcher.retry(*claims[0], ValueError("private details"))
    async with routes.app.state.database.sessions() as s:
        row = await s.get(NotificationOutbox, claims[0][0])
        assert row.status == "failed" and row.last_error == "ValueError"
    for task in claims[1:]:
        assert await dispatcher.deliver(*task)
        assert await dispatcher.acknowledge(*task)


async def test_issue_contract_status_permissions_and_no_learning(routes):
    owner, reader, rid, base, issue, user = await setup(routes)
    url = base + "/" + issue["id"]
    assert (await routes.client.get(base)).status_code == 401
    assert (await routes.client.get(url, headers=reader)).status_code == 200
    for extra in ({"nodeId": "1"}, {"releaseId": "1"}, {"type": "bug"}):
        assert (
            await routes.client.post(
                base, headers=reader, json={"title": "t", "body": "b", **extra}
            )
        ).status_code == 422
    outsider, _ = await routes.register()
    other = headers(await routes.login(outsider))
    assert (
        await routes.client.patch(
            url + "/state", headers=other, json={"status": "resolved", "expectedStatus": "open"}
        )
    ).status_code == 403
    assert (
        await routes.client.patch(
            url + "/state",
            headers=reader,
            json={"status": "closed", "expectedStatus": "open", "reason": "无关"},
        )
    ).status_code == 403
    assert (
        await routes.client.patch(
            url + "/state", headers=owner, json={"status": "resolved", "expectedStatus": "open"}
        )
    ).status_code == 200
    assert (
        await routes.client.post(url + "/comments", headers=other, json={"body": "已解决仍可补充"})
    ).status_code == 201
    assert (
        await routes.client.patch(
            url + "/state", headers=owner, json={"status": "closed", "expectedStatus": "resolved"}
        )
    ).status_code == 422
    assert (
        await routes.client.patch(
            url + "/state",
            headers=owner,
            json={"status": "closed", "expectedStatus": "resolved", "reason": "重复话题"},
        )
    ).status_code == 200
    assert (
        await routes.client.post(url + "/comments", headers=reader, json={"body": "关闭后拒绝"})
    ).status_code == 409
    assert (
        await routes.client.patch(
            url + "/state",
            headers=owner,
            json={"status": "open", "expectedStatus": "closed", "reason": "继续验证"},
        )
    ).status_code == 200
    detail = (await routes.client.get(url, headers=reader)).json()["data"]
    assert [x["type"] for x in detail["events"]] == ["created", "resolved", "closed", "reopened"]
    async with routes.app.state.database.sessions() as s:
        assert (
            await s.scalar(
                select(func.count())
                .select_from(UserRoadmap)
                .where(UserRoadmap.user_id == int(user["id"]))
            )
            == 0
        )


async def test_comments_cross_topic_anchor_edit_and_deleted_placeholders(routes):
    owner, reader, rid, base, issue, _ = await setup(routes)
    url = base + "/" + issue["id"]
    second = (
        await routes.client.post(base, headers=reader, json={"title": "另一个问题", "body": "独立"})
    ).json()["data"]
    foreign = (
        await routes.client.post(
            base + "/" + second["id"] + "/comments", headers=owner, json={"body": "另一话题回复"}
        )
    ).json()["data"]["commentId"]
    assert (
        await routes.client.post(
            url + "/comments", headers=reader, json={"body": "跨话题", "replyToCommentId": foreign}
        )
    ).status_code == 404
    cid = (
        await routes.client.post(url + "/comments", headers=owner, json={"body": "替代资源已发布"})
    ).json()["data"]["commentId"]
    await routes.client.post(
        url + "/comments", headers=reader, json={"body": "引用验证", "replyToCommentId": cid}
    )
    detail = (await routes.client.get(url, headers=owner)).json()["data"]
    row = detail["comments"]["items"][0]
    assert (
        await routes.client.patch(
            url + "/comments/" + cid,
            headers=reader,
            json={"body": "越权", "expectedUpdatedAt": row["updatedAt"]},
        )
    ).status_code == 403
    assert (
        await routes.client.patch(
            url + "/comments/" + cid,
            headers=owner,
            json={"body": "编辑后的资源说明", "expectedUpdatedAt": row["updatedAt"]},
        )
    ).status_code == 200
    assert (
        await routes.client.patch(
            url + "/comments/" + cid,
            headers=owner,
            json={"body": "旧编辑", "expectedUpdatedAt": row["updatedAt"]},
        )
    ).status_code == 409
    assert (await routes.client.delete(url + "/comments/" + cid, headers=owner)).status_code == 200
    rows = (await routes.client.get(url, headers=reader)).json()["data"]["comments"]["items"]
    assert rows[0]["body"] is None and rows[0]["replies"]["items"][0]["replyToCommentId"] == cid
    assert (await routes.client.delete(url, headers=reader)).status_code == 200
    assert (await routes.client.get(url, headers=owner)).json()["data"]["body"] is None
    assert (
        await routes.client.post(url + "/comments", headers=owner, json={"body": "删除后拒绝"})
    ).status_code == 409


async def test_outbox_dedup_unsubscribe_direct_reply_and_read_permissions(routes):
    owner, reader, rid, base, issue, user = await setup(routes)
    url = base + "/" + issue["id"]
    await drain(routes)
    assert (await routes.client.get("/api/v1/notifications/unread-count", headers=owner)).json()[
        "data"
    ]["count"] == 1
    cid = (
        await routes.client.post(url + "/comments", headers=owner, json={"body": "替代资源"})
    ).json()["data"]["commentId"]
    await drain(routes)
    assert (await routes.client.get("/api/v1/notifications/unread-count", headers=reader)).json()[
        "data"
    ]["count"] == 1
    # 作者退订不被后续回帖覆盖；直接锚点回复仍可通知被回复者。
    await routes.client.put(url + "/subscription", headers=owner, json={"subscribed": False})
    await routes.client.post(
        url + "/comments", headers=reader, json={"body": "普通回复不提醒退订作者"}
    )
    await drain(routes)
    assert (await routes.client.get("/api/v1/notifications/unread-count", headers=owner)).json()[
        "data"
    ]["count"] == 1
    await routes.client.post(
        url + "/comments",
        headers=reader,
        json={"body": "直接请求作者确认", "replyToCommentId": cid},
    )
    await drain(routes)
    listing = (await routes.client.get("/api/v1/notifications", headers=owner)).json()["data"]
    assert listing["total"] == 2
    nid = listing["items"][0]["id"]
    assert (
        await routes.client.get(f"/api/v1/notifications/{nid}/target", headers=reader)
    ).status_code == 404
    assert (
        await routes.client.patch(f"/api/v1/notifications/{nid}/read", headers=reader)
    ).status_code == 404
    target = (await routes.client.get(f"/api/v1/notifications/{nid}/target", headers=owner)).json()[
        "data"
    ]
    assert target["accessible"] and "commentId=" in target["path"]
    await routes.client.patch("/api/v1/notifications/read", headers=owner, json={"throughId": nid})
    assert (await routes.client.get("/api/v1/notifications/unread-count", headers=owner)).json()[
        "data"
    ]["count"] == 0
    async with routes.app.state.database.sessions() as s, s.begin():
        await s.execute(
            update(SkillRoadmap)
            .where(SkillRoadmap.id == int(rid))
            .values(moderation_status="disabled")
        )
    assert not (
        await routes.client.get(f"/api/v1/notifications/{nid}/target", headers=owner)
    ).json()["data"]["accessible"]
    assert (await routes.client.get(url, headers=reader)).status_code == 404


async def test_notification_delete_is_private_hidden_and_not_redelivered(routes):
    owner, reader, rid, base, issue, _ = await setup(routes)
    await drain(routes)
    endpoint = "/api/v1/notifications"
    before = (await routes.client.get(endpoint, headers=owner)).json()["data"]
    nid = before["items"][0]["id"]
    assert (await routes.client.delete(endpoint + "/" + nid, headers=reader)).status_code == 404
    assert (await routes.client.delete(endpoint + "/" + nid, headers=owner)).status_code == 200
    assert (await routes.client.delete(endpoint + "/" + nid, headers=owner)).status_code == 200
    assert (await routes.client.get(endpoint, headers=owner)).json()["data"]["total"] == 0
    assert (await routes.client.get(endpoint + "/unread-count", headers=owner)).json()["data"][
        "count"
    ] == 0
    assert (
        await routes.client.get(endpoint + "/" + nid + "/target", headers=owner)
    ).status_code == 404
    assert (
        await routes.client.patch(endpoint + "/" + nid + "/read", headers=owner)
    ).status_code == 404
    async with routes.app.state.database.sessions() as s, s.begin():
        await s.execute(
            update(NotificationOutbox)
            .where(
                NotificationOutbox.event_type == "issue_created",
                NotificationOutbox.payload["issueId"].as_integer() == int(issue["id"]),
            )
            .values(status="pending", available_at=now())
        )
    await drain(routes)
    assert (await routes.client.get(endpoint, headers=owner)).json()["data"]["total"] == 0
    assert (await routes.client.get(base + "/" + issue["id"], headers=reader)).status_code == 200


async def test_notification_bulk_delete_keeps_new_arrivals_and_other_recipients(routes):
    owner, reader, rid, base, issue, _ = await setup(routes)
    await drain(routes)
    endpoint = "/api/v1/notifications"
    original = (await routes.client.get(endpoint, headers=owner)).json()["data"]
    watermark = original["latestId"]
    await routes.client.patch(endpoint + "/" + watermark + "/read", headers=owner)
    topic = base + "/" + issue["id"]
    await routes.client.post(topic + "/comments", headers=reader, json={"body": "操作期间新到达"})
    await routes.client.post(topic + "/comments", headers=owner, json={"body": "另一收件人的通知"})
    await drain(routes)
    before = (await routes.client.get(endpoint, headers=owner)).json()["data"]
    assert before["total"] == 2
    response = await routes.client.request(
        "DELETE", endpoint, headers=owner, json={"throughId": watermark, "readOnly": True}
    )
    assert response.status_code == 200 and response.json()["data"]["deletedCount"] == 1
    remaining = (await routes.client.get(endpoint, headers=owner)).json()["data"]
    assert remaining["total"] == 1 and remaining["latestId"] != watermark
    assert (await routes.client.get(endpoint, headers=reader)).json()["data"]["total"] == 1
    assert (
        await routes.client.request(
            "DELETE", endpoint, headers=owner, json={"throughId": watermark}
        )
    ).json()["data"]["deletedCount"] == 0
    assert (await routes.client.get(endpoint + "/unread-count", headers=owner)).json()["data"][
        "count"
    ] == 1
    assert (
        await routes.client.request(
            "DELETE", endpoint, headers=owner, json={"throughId": remaining["latestId"]}
        )
    ).json()["data"]["deletedCount"] == 1
    assert (await routes.client.get(endpoint, headers=reader)).json()["data"]["total"] == 1


async def test_deleted_comment_notice_can_be_removed_without_touching_topic(routes):
    owner, reader, rid, base, issue, _ = await setup(routes)
    topic = base + "/" + issue["id"]
    comment = (
        await routes.client.post(
            topic + "/comments", headers=owner, json={"body": "之后删除的回复"}
        )
    ).json()["data"]["commentId"]
    await drain(routes)
    endpoint = "/api/v1/notifications"
    nid = (await routes.client.get(endpoint, headers=reader)).json()["data"]["items"][0]["id"]
    assert (
        await routes.client.delete(topic + "/comments/" + comment, headers=owner)
    ).status_code == 200
    assert not (await routes.client.get(endpoint + "/" + nid + "/target", headers=reader)).json()[
        "data"
    ]["accessible"]
    assert (await routes.client.delete(endpoint + "/" + nid, headers=reader)).status_code == 200
    assert (await routes.client.get(topic, headers=reader)).status_code == 200
    assert (await routes.client.get(endpoint, headers=reader)).json()["data"]["total"] == 0


async def test_notification_delete_last_page_clamps_to_remaining_page(routes):
    owner, reader, rid, base, issue, _ = await setup(routes)
    await drain(routes)
    # 分页测试直接准备通知，不通过大量发帖绕过真实讨论防刷规则。
    from uuid import uuid4

    async with routes.app.state.database.sessions() as s, s.begin():
        original = await s.scalar(select(Notification).where(Notification.roadmap_id == int(rid)))
        for _ in range(22):
            s.add(
                Notification(
                    recipient_id=original.recipient_id,
                    actor_id=original.actor_id,
                    notification_type="issue_created",
                    event_key="pagination:" + uuid4().hex,
                    roadmap_id=int(rid),
                    issue_id=int(issue["id"]),
                )
            )
    endpoint = "/api/v1/notifications"
    last = (await routes.client.get(endpoint + "?page=2", headers=owner)).json()["data"]
    assert len(last["items"]) == 3 and int(last["latestId"]) > int(last["items"][0]["id"])
    assert (
        await routes.client.request(
            "DELETE", endpoint, headers=owner, json={"throughId": last["items"][0]["id"]}
        )
    ).status_code == 200
    result = (await routes.client.get(endpoint + "?page=2", headers=owner)).json()["data"]
    assert result["page"] == 1 and result["total"] == 20 and len(result["items"]) == 20


async def test_crash_after_insert_lease_recovery_stale_token_and_retry(routes):
    owner, reader, rid, base, issue, _ = await setup(routes)
    dispatcher = OutboxDispatcher(routes.app.state.database, routes.app.state.settings)
    # 排掉发布事件，直接处理新话题。
    task = await dispatcher.claim()
    assert await dispatcher.deliver(*task)
    await dispatcher.acknowledge(*task)
    task = await dispatcher.claim()
    assert await dispatcher.deliver(*task)
    # 通知已写但未确认，模拟进程崩溃，租约过期后领取新token。
    async with routes.app.state.database.sessions() as s, s.begin():
        await s.execute(
            update(NotificationOutbox)
            .where(NotificationOutbox.id == task[0])
            .values(lease_until=now() - timedelta(seconds=1))
        )
    recovered = await dispatcher.claim()
    assert recovered[0] == task[0] and recovered[1] != task[1]
    assert not await dispatcher.deliver(*task)
    assert not await dispatcher.acknowledge(*task)
    assert await dispatcher.deliver(*recovered)
    assert await dispatcher.acknowledge(*recovered)
    async with routes.app.state.database.sessions() as s:
        assert (
            await s.scalar(
                select(func.count())
                .select_from(Notification)
                .where(Notification.issue_id == int(issue["id"]))
            )
            == 1
        )
    await routes.client.post(
        base + "/" + issue["id"] + "/comments", headers=owner, json={"body": "重试测试"}
    )
    task = await dispatcher.claim()
    await dispatcher.retry(*task, RuntimeError("secret must not be stored"))
    async with routes.app.state.database.sessions() as s, s.begin():
        row = await s.get(NotificationOutbox, task[0])
        assert row.status == "pending" and row.last_error == "RuntimeError"
        row.available_at = now() - timedelta(seconds=1)
    await drain(routes)


async def test_business_rollback_and_concurrent_close(routes):
    owner, reader, rid, base, issue, _ = await setup(routes)
    url = base + "/" + issue["id"]
    original = AsyncSession.flush

    async def fail_outbox(s, *a, **kw):
        if any(
            isinstance(x, NotificationOutbox) and x.event_type == "comment_created" for x in s.new
        ):
            raise RuntimeError("test-only outbox failure")
        return await original(s, *a, **kw)

    with patch.object(AsyncSession, "flush", fail_outbox), pytest.raises(RuntimeError):
        await routes.client.post(url + "/comments", headers=reader, json={"body": "必须回滚"})
    assert (await routes.client.get(url, headers=owner)).json()["data"]["comments"]["total"] == 0
    results = await asyncio.gather(
        routes.client.patch(
            url + "/state",
            headers=owner,
            json={"status": "closed", "expectedStatus": "open", "reason": "停止讨论"},
        ),
        routes.client.post(url + "/comments", headers=reader, json={"body": "并发回复"}),
    )
    assert results[0].status_code == 200
    assert results[1].status_code in (201, 409)
    assert (
        await routes.client.post(url + "/comments", headers=reader, json={"body": "关闭提交后拒绝"})
    ).status_code == 409


async def test_delivery_rechecks_unsubscribe_disabled_and_release_subscriptions(routes):
    owner, reader, rid, base, issue, user = await setup(routes)
    await routes.client.put(
        base + "/" + issue["id"] + "/subscription", headers=owner, json={"subscribed": False}
    )
    await drain(routes)
    assert (await routes.client.get("/api/v1/notifications", headers=owner)).json()["data"][
        "total"
    ] == 0
    async with routes.app.state.database.sessions() as s, s.begin():
        s.add(RoadmapSubscription(roadmap_id=int(rid), user_id=int(user["id"]), is_subscribed=1))
    token = owner["Authorization"].split()[1]
    doc = (await routes.client.get(f"/api/v1/roadmaps/{rid}/draft", headers=owner)).json()["data"][
        "document"
    ]
    doc["title"] = "替代资源版"
    doc = await save(routes, token, rid, doc)
    assert (await publish(routes, token, rid, doc, "替代资源")).status_code == 200
    await drain(routes)
    rows = (await routes.client.get("/api/v1/notifications", headers=reader)).json()["data"][
        "items"
    ]
    assert [r["type"] for r in rows] == ["release_published"]
    await routes.client.post(
        base + "/" + issue["id"] + "/comments", headers=owner, json={"body": "禁用后不投递"}
    )
    async with routes.app.state.database.sessions() as s, s.begin():
        await s.execute(update(User).where(User.id == int(user["id"])).values(status="disabled"))
    await drain(routes)
    async with routes.app.state.database.sessions() as s:
        assert (
            await s.scalar(
                select(func.count())
                .select_from(Notification)
                .where(Notification.recipient_id == int(user["id"]))
            )
            == 1
        )
