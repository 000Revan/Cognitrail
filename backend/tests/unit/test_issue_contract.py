"""R07 话题输入不接受版本绑定，状态和引用使用严格契约。"""

import pytest
from pydantic import ValidationError

from app.schemas.issue import CommentCreate, DeleteNotifications, IssueCreate, IssueState
from app.schemas.moderation import InvalidateCheckin, ReportCreate, ReportHandle


def test_report_accepts_single_controlled_target_and_forbids_privileged_fields():
    for extra in ({"reporterId": "1"}, {"status": "resolved"}, {"roadmapId": "2"}):
        with pytest.raises(ValidationError):
            ReportCreate(targetType="comment", targetId="1", reasonCode="spam", **extra)
    for kind in ("user", "release", "checkin"):
        with pytest.raises(ValidationError):
            ReportCreate(targetType=kind, targetId="1", reasonCode="spam")


def test_governance_requires_reason_strict_expected_validity_and_open_report_status():
    with pytest.raises(ValidationError):
        ReportHandle(expectedStatus="pending", status="resolved", reason="  ")
    with pytest.raises(ValidationError):
        ReportHandle(expectedStatus="resolved", status="resolved", reason="重复结案")
    with pytest.raises(ValidationError):
        InvalidateCheckin(reason="撤销", expectedValid=1)


def test_topic_only_accepts_free_title_body():
    assert IssueCreate(title=" 资源失效 ", body="链接打不开").title == "资源失效"
    for extra in ({"nodeId": "1"}, {"releaseId": "1"}, {"type": "bug"}):
        with pytest.raises(ValidationError):
            IssueCreate(title="资源失效", body="链接打不开", **extra)


@pytest.mark.parametrize("value", ["", "  ", "x" * 151])
def test_invalid_title(value):
    with pytest.raises(ValidationError):
        IssueCreate(title=value, body="正文")


def test_closing_requires_reason_and_forbids_unknown_status():
    for payload in (
        {"status": "closed", "expectedStatus": "open"},
        {"status": "hidden", "expectedStatus": "open", "reason": "管理"},
    ):
        with pytest.raises(ValidationError):
            IssueState(**payload)
    assert IssueState(status="closed", expectedStatus="open", reason="重复话题").reason


def test_comment_reference_rejects_non_id():
    with pytest.raises(ValidationError):
        CommentCreate(body="回复", replyToCommentId=0)


def test_notification_bulk_delete_requires_explicit_watermark_and_strict_scope():
    assert not DeleteNotifications(throughId="123").read_only
    for payload in (
        {},
        {"throughId": "0"},
        {"throughId": "1", "readOnly": 1},
        {"throughId": "1", "userId": "2"},
    ):
        with pytest.raises(ValidationError):
            DeleteNotifications(**payload)
