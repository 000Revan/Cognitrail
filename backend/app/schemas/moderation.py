"""举报和治理输入：单一目标、受控动作及预期状态。"""

from typing import Annotated, Literal

from pydantic import ConfigDict, Field, StringConstraints

from app.schemas.common import JsonId, Schema

Reason = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=1000)
]


class ReportCreate(Schema):
    """一个请求只关联一个可访问目标，不接受客户端处理状态。"""

    model_config = ConfigDict(extra="forbid")
    target_type: Literal["roadmap", "issue", "comment"]
    target_id: JsonId
    reason_code: Literal["spam", "copyright", "abuse", "unsafe", "other"]
    description: Annotated[
        str, StringConstraints(strict=True, strip_whitespace=True, max_length=2000)
    ] = ""


class ReportHandle(Schema):
    """结案与治理在同一事务提交，旧状态冲突拒绝覆盖。"""

    model_config = ConfigDict(extra="forbid")
    expected_status: Literal["pending", "processing"]
    status: Literal["processing", "resolved", "rejected"]
    action: Literal["none", "disable", "hide", "restore"] = "none"
    reason: Reason


class InvalidateCheckin(Schema):
    """只允许撤销事实有效性，不读取用户学习正文或修改日期。"""

    model_config = ConfigDict(extra="forbid")
    reason: Reason
    expected_valid: bool = Field(strict=True)
