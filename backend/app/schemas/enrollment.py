"""R05 单关系、绑定会话、位置、完成与每日打卡契约。"""

from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from app.schemas.common import JsonId, Schema


class EnrollRequest(Schema):
    """首次开始绑定所见版本；恢复由独立接口明确执行。"""

    model_config = ConfigDict(extra="forbid")
    release_id: JsonId


class SessionWrite(Schema):
    """所有学习写操作显式携带当前会话，拒绝旧标签页写入。"""

    model_config = ConfigDict(extra="forbid")
    session_id: JsonId


class UpdatePrompt(Schema):
    """只针对明确所见的发布版抑制提示，不影响始终可见的新版标记。"""

    model_config = ConfigDict(extra="forbid")
    release_id: JsonId
    dismissed: bool = Field(strict=True)


class PositionUpdate(SessionWrite):
    node_id: JsonId


class NodeStatusUpdate(SessionWrite):
    completed: bool = Field(strict=True)


class StudyRecordCreate(SessionWrite):
    """只记录服务端日期事实，无客户端日期、收获和时长。"""


class EnrollmentSummary(Schema):
    id: str
    roadmap_id: str
    session_id: str
    release_id: str
    version_no: int
    title: str
    description: str | None
    difficulty: str | None
    status: Literal["active", "abandoned"]
    started_at: str
    abandoned_at: str | None
    completed_at: str | None
    last_node_id: str | None
    last_opened_at: str | None
    progress_version: int
    content_available: bool
    writable: bool
    has_new_version: bool
    update_prompt_dismissed: bool = False
    current_version_no: int | None
    current_release_id: str | None = None
    stage_count: int
    node_count: int
    completed_node_count: int
    progress_node_count: int
    progress_percent: int
    is_current_session: bool = True


class EnrollmentPage(Schema):
    items: list[EnrollmentSummary]
    total: int
    page: int
    page_size: int


class NodeProgress(Schema):
    release_node_id: str
    completed: bool
    completed_at: str | None


class LearningResource(Schema):
    id: str
    title: str
    resource_type: str
    resource_url: str
    language_code: str | None
    access_type: str


class LearningNode(Schema):
    id: str
    title: str
    content: str
    estimated_minutes: int | None
    tips: str | None
    canvas_x: float
    canvas_y: float
    is_optional: bool
    counts_toward_progress: bool
    resources: list[LearningResource]


class LearningStage(Schema):
    id: str
    title: str
    description: str | None
    canvas_x: float
    canvas_y: float
    nodes: list[LearningNode]


class LearningConnection(Schema):
    source: str
    target: str


class EnrollmentContent(Schema):
    enrollment: EnrollmentSummary
    stages: list[LearningStage]
    connections: list[LearningConnection]
    progress: list[NodeProgress]
    visited_resource_ids: list[str] = Field(default_factory=list)


class StudyRecordResult(Schema):
    id: str
    session_id: str
    checkin_date: str
    timezone_name: str
    is_valid: bool
    created_at: str


class StudyRecordPage(Schema):
    items: list[StudyRecordResult]
    total: int
    today: str
    checked_in_today: bool
    page: int
    page_size: int


class LearningOverview(Schema):
    learning_roadmap_count: int
    completed_node_count: int
    checkin_day_count: int
    current_streak: int
    longest_streak: int
    today: str
    month: str
    calendar_dates: list[str]


class UpgradeConfirmation(Schema):
    """只对服务端指定的语义修订节点明确选择保留或重学。"""

    model_config = ConfigDict(extra="forbid")
    stable_key: UUID
    action: Literal["keep", "relearn"]


class UpgradeRequest(Schema):
    """绑定预览的源会话、目标版和进度版本，UUID支持丢响应后的安全重试。"""

    model_config = ConfigDict(extra="forbid")
    source_session_id: JsonId
    target_release_id: JsonId
    progress_version: int = Field(strict=True, ge=1)
    request_key: UUID
    confirmations: list[UpgradeConfirmation] = Field(max_length=10000)

    @model_validator(mode="after")
    def unique_confirmations(self):
        """拒绝重复身份，避免客户端与服务端以不同顺序解释选择。"""
        keys = [item.stable_key for item in self.confirmations]
        if len(keys) != len(set(keys)):
            raise ValueError("同一节点不能重复确认")
        return self


class UpgradeNodeDifference(Schema):
    stable_key: str
    source_title: str | None
    target_title: str | None
    source_stage: str | None
    target_stage: str | None
    changes: list[str]
    is_completed: bool
    requires_confirmation: bool
    source_excerpt: str | None = None
    target_excerpt: str | None = None
    target_counts_toward_progress: bool


class UpgradeStageDifference(Schema):
    stable_key: str
    source_title: str | None
    target_title: str | None
    changes: list[str]


class UpgradePreview(Schema):
    source_session_id: str
    target_release_id: str
    source_version_no: int
    target_version_no: int
    progress_version: int
    update_summary: str
    source_completed: int
    source_total: int
    source_percent: int
    target_total: int
    completed_min: int
    completed_max: int
    percent_min: int
    percent_max: int
    node_changes: list[UpgradeNodeDifference]
    stage_changes: list[UpgradeStageDifference]
    release_changes: list[str]
    connections_changed: bool


class UpgradeResult(Schema):
    """升级回执不含课程正文，重复请求可返回原始同一回执。"""

    source_session_id: str
    target_session_id: str
    target_release_id: str
    version_no: int
    progress_version: int
    completed_node_count: int
    progress_node_count: int
    progress_percent: int
    last_node_id: str | None
