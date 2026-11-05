"""S03完整工作稿与公开结构契约；公开节点不含正文、资源或提示。"""

import re
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator, model_validator

from app.config.enums import Difficulty, ResourceType, RoadmapType
from app.schemas.common import Schema
from app.schemas.fields import NonnegativeVersion, PositiveMinutes

ContentId = Annotated[str, Field(pattern=r"^(?:[1-9][0-9]{0,18}|tmp_[A-Za-z0-9_-]{1,64})$")]
Coordinate = Annotated[float, Field(ge=0, le=10000, allow_inf_nan=False)]


def valid_web_url(value: str | None) -> str | None:
    """仅允许无凭证的HTTP/HTTPS链接，不请求外站，不接受脚本或本地文件。"""
    if not value:
        return value
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username:
        raise ValueError("请输入有效的HTTP/HTTPS链接")
    if any(ord(char) < 33 for char in value) or len(value) > 2048:
        raise ValueError("链接包含空白或长度超过2048")
    try:
        _ = parts.port
    except ValueError as cause:
        raise ValueError("链接端口无效") from cause
    return value


class Input(Schema):
    """拒绝客户端越权设置创建者、状态、发布版本等字段。"""

    model_config = ConfigDict(extra="forbid")


class ResourceInput(Input):
    id: ContentId
    title: str = Field(default="", max_length=200)
    resource_type: ResourceType = ResourceType.ARTICLE
    resource_url: str = Field(default="", max_length=2048)
    language_code: str | None = Field(default=None, max_length=16)
    access_type: Literal["free", "paid", "freemium", "unknown"] = "unknown"
    _url = field_validator("resource_url")(valid_web_url)


class NodeInput(Input):
    id: ContentId
    stable_key: UUID | None = None
    revision_no: Annotated[int, Field(strict=True, ge=1, le=4294967295)] | None = None
    title: str = Field(default="", max_length=150)
    content: str = Field(default="", max_length=10000)
    estimated_minutes: PositiveMinutes | None = None
    tips: str | None = Field(default=None, max_length=10000)
    canvas_x: Coordinate = 24
    canvas_y: Coordinate = 72
    is_optional: bool = False
    counts_toward_progress: bool = True
    change_policy: Literal["retain", "reconfirm"] = "retain"
    resources: list[ResourceInput] = Field(default_factory=list, max_length=30)


class StageInput(Input):
    id: ContentId
    stable_key: UUID | None = None
    title: str = Field(default="", max_length=120)
    description: str | None = Field(default=None, max_length=10000)
    canvas_x: Coordinate = 40
    canvas_y: Coordinate = 40
    nodes: list[NodeInput] = Field(default_factory=list, max_length=80)


class Connection(Input):
    source: ContentId
    target: ContentId


class RoadmapCreate(Input):
    title: str = Field(default="未命名路线", min_length=1, max_length=120)
    roadmap_type: RoadmapType = RoadmapType.USER

    @field_validator("title")
    @classmethod
    def nonblank_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("路线标题不能为空")
        return value.strip()


class VersionAction(Input):
    expected_version: NonnegativeVersion


class PublishAction(VersionAction):
    """发布更新说明与工作稿乐观锁一并提交。"""

    update_summary: str = Field(min_length=1, max_length=2000)

    @field_validator("update_summary")
    @classmethod
    def nonblank_summary(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("请填写更新说明")
        return value.strip()


class RoadmapDisable(VersionAction):
    """仅下架整条来源；原因去首尾空白后须为1至1000字。"""

    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, value):
        return value.strip() if isinstance(value, str) else value


class RoadmapSave(VersionAction):
    title: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    effort_note: str | None = Field(default=None, max_length=200)
    license_code: Literal["UNSPECIFIED", "UNLICENSED", "CC-BY-4.0", "CC-BY-SA-4.0", "custom"] = (
        "UNSPECIFIED"
    )
    license_url: str | None = Field(default=None, max_length=2048)
    difficulty: Difficulty = Difficulty.BEGINNER
    cover_url: None = None
    stages: list[StageInput] = Field(default_factory=list, max_length=40)
    connections: list[Connection] = Field(default_factory=list, max_length=200)
    _license_url = field_validator("license_url")(valid_web_url)
    _url = field_validator("cover_url")(valid_web_url)

    @field_validator("title")
    @classmethod
    def nonblank_title(cls, value: str) -> str:
        return RoadmapCreate.nonblank_title(value)

    @model_validator(mode="after")
    def validate_graph(self):
        """完整图校验：端点存在、同类ID唯一、无自连/重复边，允许有向回路。"""
        for stage in self.stages:
            for node in stage.nodes:
                if node.is_optional and node.counts_toward_progress:
                    raise ValueError("拓展节点不能计入主线进度")
                if any(r.resource_type.value == "document" for r in node.resources):
                    raise ValueError("资源类型请选择文章、视频、课程、书籍或其他")
        groups = [
            [s.id for s in self.stages],
            [n.id for s in self.stages for n in s.nodes],
            [r.id for s in self.stages for n in s.nodes for r in n.resources],
        ]
        if len(groups[1]) > 500 or len(groups[2]) > 1500:
            raise ValueError("路线最多500个节点、1500项资源")
        temporary = []
        for ids in groups:
            if len(ids) != len(set(ids)):
                raise ValueError("重复的内容ID")
            temporary.extend(x for x in ids if x.startswith("tmp_"))
            if any(x.isdecimal() and int(x) > 9223372036854775807 for x in ids):
                raise ValueError("内容ID超出BIGINT范围")
        if len(temporary) != len(set(temporary)):
            raise ValueError("临时ID必须全局唯一")
        edges = set()
        for edge in self.connections:
            pair = (edge.source, edge.target)
            if edge.source not in groups[0] or edge.target not in groups[0]:
                raise ValueError("连线端点必须属于当前路线")
            if edge.source == edge.target or pair in edges:
                raise ValueError("不支持自连或重复连线")
            edges.add(pair)
        return self


def content_key(value: str) -> int | None:
    """临时ID不转换为数据库ID；真实ID只在通过schema后读取。"""
    return int(value) if re.fullmatch(r"[1-9][0-9]*", value) else None
