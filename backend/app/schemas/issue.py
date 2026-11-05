"""R07 话题、平铺回复和通知请求契约。"""

from typing import Annotated, Literal

from pydantic import ConfigDict, Field, StringConstraints, model_validator

from app.schemas.common import JsonId, Schema

Body = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=20000)
]
Title = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=150)
]
Status = Literal["open", "resolved", "closed"]


class IssueCreate(Schema):
    """话题仅由路由参数关联路线，不收集学习版本。"""

    model_config = ConfigDict(extra="forbid")
    title: Title
    body: Body


class IssueEdit(IssueCreate):
    """时间戳作为编辑冲突令牌，防止静默覆盖。"""

    expected_updated_at: str = Field(min_length=1, max_length=40)


class CommentCreate(Schema):
    """引用必须在服务端复核属于同话题。"""

    model_config = ConfigDict(extra="forbid")
    body: Body
    reply_to_comment_id: JsonId | None = None


class CommentEdit(Schema):
    """本人回复编辑，禁止改写引用目标。"""

    model_config = ConfigDict(extra="forbid")
    body: Body
    expected_updated_at: str = Field(min_length=1, max_length=40)


class IssueState(Schema):
    """解决、关闭、重新打开均带预期状态；关闭必填原因。"""

    model_config = ConfigDict(extra="forbid")
    status: Status
    expected_status: Status
    reason: (
        Annotated[str, StringConstraints(strict=True, strip_whitespace=True, max_length=500)] | None
    ) = None

    @model_validator(mode="after")
    def closing_reason(self):
        """关闭原因是处理事实，不能留空。"""
        if self.status == "closed" and not self.reason:
            raise ValueError("关闭话题必须填写原因")
        return self


class SubscriptionChange(Schema):
    """退订持久保留，不因作者身份或发言自动恢复。"""

    model_config = ConfigDict(extra="forbid")
    subscribed: Annotated[bool, Field(strict=True)]


class ReadNotifications(Schema):
    """仅将明确选定的通知设已读；全读使用当前列表边界。"""

    model_config = ConfigDict(extra="forbid")
    through_id: JsonId


class DeleteNotifications(ReadNotifications):
    """仅清理已取得的消息边界；新到达消息不受影响。"""

    read_only: Annotated[bool, Field(strict=True)] = False
