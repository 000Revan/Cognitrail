"""公开社区数据模型：node_resources。"""

from datetime import datetime

from sqlalchemy import ForeignKeyConstraint, UniqueConstraint, text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import TABLE_OPTIONS, Base


class NodeResource(Base):
    """按位置排序的外链资源，协议安全由服务层校验。"""

    __tablename__ = "node_resources"
    __table_args__ = (
        UniqueConstraint("node_id", "position", name="uq_node_resources_1"),
        ForeignKeyConstraint(
            ["node_id"],
            ["learning_nodes.id"],
            name="fk_node_resources_1",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=True,
        primary_key=True,
        comment="资源标识",
    )
    node_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="所属节点",
    )
    title: Mapped[str] = mapped_column(
        mysql.VARCHAR(length=200),
        nullable=False,
        autoincrement=False,
        comment="资源名称",
    )
    url: Mapped[str] = mapped_column(
        mysql.VARCHAR(length=2048),
        nullable=False,
        autoincrement=False,
        comment="外链地址",
    )
    resource_type: Mapped[str] = mapped_column(
        mysql.VARCHAR(charset="ascii", collation="ascii_bin", length=16),
        nullable=False,
        autoincrement=False,
        comment="article或video或course或book或other",
    )
    language_code: Mapped[str | None] = mapped_column(
        mysql.VARCHAR(length=16),
        nullable=True,
        autoincrement=False,
        comment="语言标识，如zh-CN",
    )
    access_type: Mapped[str] = mapped_column(
        mysql.VARCHAR(charset="ascii", collation="ascii_bin", length=16),
        nullable=False,
        autoincrement=False,
        server_default=text("'unknown'"),
        comment="free或paid或freemium或unknown",
    )
    position: Mapped[int] = mapped_column(
        mysql.INTEGER(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="节点内资源顺序，正整数",
    )
    created_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=False,
        autoincrement=False,
        server_default=text("CURRENT_TIMESTAMP(6)"),
        comment="创建时间 UTC",
    )
    updated_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=False,
        autoincrement=False,
        server_default=text("CURRENT_TIMESTAMP(6)"),
        comment="修改时间 UTC，由服务层更新",
    )
