"""业务 schema 可复用的字段约束；数据库触发器提供额外写入保护。"""

from typing import Annotated

from pydantic import Field

PositiveMinutes = Annotated[int, Field(strict=True, gt=0, le=2147483647)]
NonnegativeVersion = Annotated[int, Field(strict=True, ge=0)]
OptionalStudyText = Annotated[str | None, Field(max_length=10000)]
