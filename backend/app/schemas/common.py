"""统一响应与序列化契约。"""

from datetime import UTC, datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, WithJsonSchema
from pydantic.alias_generators import to_camel


def serialize_id(value: int) -> str:
    """BIGINT 在 JSON 中输出十进制字符串，避免浏览器精度丢失。"""
    return str(value)


def serialize_utc(value: datetime) -> str:
    """数据库无时区 DATETIME 按 UTC 解读，输出带 Z 的时间。"""
    return (
        value.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")
        if (value.tzinfo is None)
        else value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    )


JsonId = Annotated[
    int,
    Field(ge=1, le=2**64 - 1),
    PlainSerializer(serialize_id, return_type=str, when_used="json"),
    WithJsonSchema({"type": "string", "pattern": "^[1-9][0-9]*$"}, mode="serialization"),
]
UtcDateTime = Annotated[datetime, PlainSerializer(serialize_utc, return_type=str)]


class Schema(BaseModel):
    """内部 snake_case，对外 camelCase。"""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
        from_attributes=True,
    )


class ApiResponse[T](Schema):
    """所有成功和失败响应使用同一外层结构。"""

    code: int = 200
    msg: str = "success"
    data: T


class ErrorData(Schema):
    error_code: str
    details: list[dict[str, Any]] | dict[str, Any] | None = None
    request_id: str


class PageParams(Schema):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class Page[T](Schema):
    items: list[T]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
