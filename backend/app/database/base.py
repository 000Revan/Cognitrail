"""全部业务表共用一个元数据及表级配置。"""

from datetime import datetime

from sqlalchemy import MetaData, text
from sqlalchemy.dialects.mysql import BIGINT, DATETIME, VARCHAR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

TABLE_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


class Base(DeclarativeBase):
    """所有模型共用的 Base。"""

    # 约束和索引在模型中显式命名，与已执行的冻结基线保持一致。
    metadata = MetaData()


class IdMixin:
    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), primary_key=True, autoincrement=True, comment="主键"
    )


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6),
        server_default=text("CURRENT_TIMESTAMP(6)"),
        comment="创建时间 UTC",
    )


class UpdatedAtMixin:
    updated_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6),
        server_default=text("CURRENT_TIMESTAMP(6)"),
        comment="修改时间 UTC，由服务层更新",
    )


def ascii_type(length: int = 16) -> VARCHAR:
    """状态和 UUID 采用 ASCII 二进制比较。"""
    return VARCHAR(length, charset="ascii", collation="ascii_bin")
