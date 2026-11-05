"""健康接口只返回非敏感运行信息。"""

from typing import Literal

from app.schemas.common import Schema, UtcDateTime


class LiveHealth(Schema):
    service: str
    status: Literal["alive"] = "alive"
    checked_at: UtcDateTime


class ReadyHealth(Schema):
    status: Literal["ready"] = "ready"
    database: Literal["connected"] = "connected"
    database_version: str
    migration_revision: str
    timezone: str
    checked_at: UtcDateTime
