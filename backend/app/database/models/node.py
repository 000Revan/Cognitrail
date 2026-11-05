"""公开社区数据模型：learning_nodes。"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint, text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import TABLE_OPTIONS, Base


class LearningNode(Base):
    """工作稿节点，以稳定身份及修订号描述学习语义变化。"""

    __tablename__ = "learning_nodes"
    __table_args__ = (
        UniqueConstraint("roadmap_id", "stable_key", name="uq_learning_nodes_1"),
        UniqueConstraint("id", "roadmap_id", name="uq_learning_nodes_2"),
        ForeignKeyConstraint(
            ["roadmap_id"],
            ["skill_roadmaps.id"],
            name="fk_learning_nodes_1",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["stage_id", "roadmap_id"],
            ["roadmap_stages.id", "roadmap_stages.roadmap_id"],
            name="fk_learning_nodes_2",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        Index("idx_learning_nodes_1", "stage_id", "is_deleted", "position"),
        Index("idx_learning_nodes_fk_2", "stage_id", "roadmap_id"),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=True,
        primary_key=True,
        comment="工作稿节点标识",
    )
    roadmap_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="所属路线，辅助一致性约束",
    )
    stage_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="所属同路线阶段",
    )
    stable_key: Mapped[str] = mapped_column(
        mysql.CHAR(charset="ascii", collation="ascii_bin", length=36),
        nullable=False,
        autoincrement=False,
        comment="任务稳定UUID",
    )
    title: Mapped[str] = mapped_column(
        mysql.VARCHAR(length=150),
        nullable=False,
        autoincrement=False,
        comment="节点标题",
    )
    content: Mapped[str | None] = mapped_column(
        mysql.MEDIUMTEXT(),
        nullable=True,
        autoincrement=False,
        comment="学习目标与说明",
    )
    tips: Mapped[str | None] = mapped_column(
        mysql.TEXT(),
        nullable=True,
        autoincrement=False,
        comment="可选提示",
    )
    position: Mapped[int] = mapped_column(
        mysql.INTEGER(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="阶段内顺序，正整数",
    )
    is_optional: Mapped[int] = mapped_column(
        mysql.TINYINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        server_default=text("0"),
        comment="是否拓展节点",
    )
    counts_toward_progress: Mapped[int] = mapped_column(
        mysql.TINYINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        server_default=text("1"),
        comment="是否计入主线进度",
    )
    revision_no: Mapped[int] = mapped_column(
        mysql.INTEGER(unsigned=True),
        nullable=False,
        autoincrement=False,
        server_default=text("1"),
        comment="学习语义修订号，正整数",
    )
    change_policy: Mapped[str] = mapped_column(
        mysql.VARCHAR(charset="ascii", collation="ascii_bin", length=16),
        nullable=False,
        autoincrement=False,
        server_default=text("'retain'"),
        comment="retain或reconfirm",
    )
    canvas_x: Mapped[Decimal] = mapped_column(
        mysql.DECIMAL(precision=12, scale=2),
        nullable=False,
        autoincrement=False,
        server_default=text("0"),
        comment="画布横坐标",
    )
    canvas_y: Mapped[Decimal] = mapped_column(
        mysql.DECIMAL(precision=12, scale=2),
        nullable=False,
        autoincrement=False,
        server_default=text("0"),
        comment="画布纵坐标",
    )
    estimated_minutes: Mapped[int | None] = mapped_column(
        mysql.INTEGER(unsigned=True),
        nullable=True,
        autoincrement=False,
        comment="选填参考分钟；空值不显示，非空须正数并注明仅供参考",
    )
    is_deleted: Mapped[int] = mapped_column(
        mysql.TINYINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        server_default=text("0"),
        comment="软删除标记",
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
