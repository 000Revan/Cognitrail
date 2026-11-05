"""R08真实MySQL：举报隐私、原子结案、隐藏占位及有效打卡重算。"""

import asyncio
import os
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.database.models import ContentReport, ModerationAction
from tests.integration.test_accounts import accounts as accounts  # noqa: F401
from tests.integration.test_accounts import headers
from tests.integration.test_issues import setup
from tests.integration.test_roadmaps import routes as routes  # noqa: F401

pytestmark = [
    pytest.mark.database,
    pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="需显式独立测试库"),
]


async def submit(routes, reader, kind, target_id):
    result = await routes.client.post(
        "/api/v1/reports",
        headers=reader,
        json={
            "targetType": kind,
            "targetId": target_id,
            "reasonCode": "spam",
            "description": "需要审核的内容",
        },
    )
    assert result.status_code == 201, result.text
    assert "reporter" not in result.text.lower()
    return result.json()["data"]


@pytest.mark.parametrize("kind", ["roadmap", "issue", "comment"])
async def test_self_report_is_rejected_without_writing_but_other_authors_remain_reportable(
    routes, kind
):
    """拒绝本人三类内容，路线作者仍可举报其他人在本人路线下发布的内容。"""
    owner, reader, rid, base, issue, user = await setup(routes)
    reply = (
        await routes.client.post(
            base + "/" + issue["id"] + "/comments", headers=reader, json={"body": "本人回复"}
        )
    ).json()["data"]["commentId"]
    target_id = rid if kind == "roadmap" else issue["id"] if kind == "issue" else reply
    own_headers = owner if kind == "roadmap" else reader
    response = await routes.client.post(
        "/api/v1/reports",
        headers=own_headers,
        json={"targetType": kind, "targetId": target_id, "reasonCode": "other"},
    )
    assert response.status_code == 403, response.text
    assert response.json()["data"]["errorCode"] == "SELF_REPORT_FORBIDDEN"
    mine = (await routes.client.get("/api/v1/reports", headers=own_headers)).json()["data"]
    assert mine["total"] == 0
    report = await submit(routes, reader if kind == "roadmap" else owner, kind, target_id)
    assert report["targetId"] == target_id
    # 规则调整不删除历史数据或改变管理员正常复核流程。
    _, token = await routes.admin()
    assert (
        await routes.client.get("/api/v1/admin/reports/" + report["id"], headers=headers(token))
    ).status_code == 200


async def test_report_privacy_claim_conflicts_and_hidden_reply_reference(routes):
    owner, reader, rid, base, issue, _ = await setup(routes)
    endpoint = base + "/" + issue["id"]
    reply = (
        await routes.client.post(
            endpoint + "/comments", headers=owner, json={"body": "待治理的回复正文"}
        )
    ).json()["data"]["commentId"]
    child = await routes.client.post(
        endpoint + "/comments",
        headers=reader,
        json={"body": "引用后继续讨论", "replyToCommentId": reply},
    )
    assert child.status_code == 201
    report = await submit(routes, reader, "comment", reply)
    assert (await submit(routes, reader, "comment", reply))["id"] == report["id"]
    mine = (await routes.client.get("/api/v1/reports", headers=owner)).json()["data"]
    assert not mine["items"]
    _, admin_token = await routes.admin()
    admin = headers(admin_token)
    url = "/api/v1/admin/reports/" + report["id"]
    assert (await routes.client.get(url, headers=reader)).status_code == 403
    details = await routes.client.get(url, headers=admin)
    assert details.json()["data"]["target"]["body"] == "待治理的回复正文"
    assert "reporter" not in details.text.lower()
    processing = {
        "expectedStatus": "pending",
        "status": "processing",
        "action": "none",
        "reason": "已受理",
    }
    assert (await routes.client.patch(url, headers=admin, json=processing)).status_code == 200
    assert (await routes.client.patch(url, headers=admin, json=processing)).status_code == 409
    payload = {
        "expectedStatus": "processing",
        "status": "resolved",
        "action": "hide",
        "reason": "确认广告，隐藏此回复",
    }
    assert (await routes.client.patch(url, headers=admin, json=payload)).status_code == 200
    detail = (await routes.client.get(endpoint, headers=reader)).json()["data"]
    assert "待治理的回复正文" not in str(detail)
    root = next(r for r in detail["comments"]["items"] if r["id"] == reply)
    assert root["visibility"] == "hidden" and root["body"] is None and root["author"] is None
    assert root["replies"]["items"][0]["replyToCommentId"] == reply
    assert root["replies"]["items"][0]["replyToAuthor"] is None
    mine = (await routes.client.get("/api/v1/reports", headers=reader)).json()["data"]
    assert mine["items"][0]["resultNote"] == payload["reason"]
    assert (
        await routes.client.post(
            endpoint + "/comments",
            headers=reader,
            json={"body": "不能回复隐藏对象", "replyToCommentId": reply},
        )
    ).status_code == 404


async def test_report_route_governance_rolls_back_and_allows_only_one_concurrent_handler(routes):
    owner, reader, rid, base, issue, _ = await setup(routes)
    report = await submit(routes, reader, "roadmap", rid)
    _, admin_token = await routes.admin()
    admin = headers(admin_token)
    url = "/api/v1/admin/reports/" + report["id"]
    payload = {
        "expectedStatus": "pending",
        "status": "resolved",
        "action": "disable",
        "reason": "审核下架",
    }
    with patch(
        "app.services.moderation_service.users.add_audit",
        side_effect=RuntimeError("atomic failure"),
    ):
        with pytest.raises(RuntimeError):
            await routes.client.patch(url, headers=admin, json=payload)
    assert (await routes.client.get(f"/api/v1/roadmaps/{rid}")).status_code == 200
    async with routes.app.state.database.sessions() as session:
        assert (await session.get(ContentReport, int(report["id"]))).status == "pending"
        assert not list(
            await session.scalars(
                select(ModerationAction).where(ModerationAction.report_id == int(report["id"]))
            )
        )
    results = await asyncio.gather(
        *(routes.client.patch(url, headers=admin, json=payload) for _ in range(2))
    )
    assert sorted(r.status_code for r in results) == [200, 409]
    assert (await routes.client.get(f"/api/v1/roadmaps/{rid}")).status_code == 404
    invalid = await routes.client.post(
        "/api/v1/reports",
        headers=reader,
        json={
            "targetType": "issue",
            "targetId": issue["id"],
            "roadmapId": rid,
            "reasonCode": "spam",
        },
    )
    assert invalid.status_code == 422


async def test_checkin_invalidation_preserves_fact_and_recalculates_private_statistics(routes):
    owner, reader, rid, base, issue, _ = await setup(routes)
    route = (await routes.client.get(f"/api/v1/roadmaps/{rid}", headers=reader)).json()["data"]
    relation = (
        await routes.client.post(
            f"/api/v1/roadmaps/{rid}/enroll", headers=reader, json={"releaseId": route["releaseId"]}
        )
    ).json()["data"]
    endpoint = "/api/v1/enrollments/" + relation["id"] + "/records"
    record = (
        await routes.client.post(
            endpoint, headers=reader, json={"sessionId": relation["sessionId"]}
        )
    ).json()["data"]
    before = (await routes.client.get("/api/v1/users/me/learning-overview", headers=reader)).json()[
        "data"
    ]
    assert before["checkinDayCount"] == 1
    _, token = await routes.admin()
    admin = headers(token)
    url = "/api/v1/admin/checkins/" + record["id"] + "/invalidate"
    payload = {"expectedValid": True, "reason": "撤销无效打卡"}
    assert (await routes.client.post(url, headers=reader, json=payload)).status_code == 403
    result = await routes.client.post(url, headers=admin, json=payload)
    assert result.status_code == 200, result.text
    assert (await routes.client.post(url, headers=admin, json=payload)).status_code == 409
    after = (await routes.client.get("/api/v1/users/me/learning-overview", headers=reader)).json()[
        "data"
    ]
    assert after["checkinDayCount"] == 0
    history = (await routes.client.get(endpoint, headers=reader)).json()["data"]
    assert history["total"] == 1 and not history["items"][0]["isValid"]
    assert history["checkedInToday"]
