"""公开社区数据模型：roadmap_stages, roadmap_stage_edges。"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint, text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import TABLE_OPTIONS, Base


class RoadmapStage(Base):
    """带稳定身份和软删除标记的工作稿阶段。"""

    __tablename__ = "roadmap_stages"
    __table_args__ = (
        UniqueConstraint("roadmap_id", "stable_key", name="uq_roadmap_stages_1"),
        UniqueConstraint("id", "roadmap_id", name="uq_roadmap_stages_2"),
        ForeignKeyConstraint(
            ["roadmap_id"],
            ["skill_roadmaps.id"],
            name="fk_roadmap_stages_1",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        Index("idx_roadmap_stages_1", "roadmap_id", "is_deleted", "position"),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=True,
        primary_key=True,
        comment="工作稿阶段标识",
    )
    roadmap_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="所属路线",
    )
    stable_key: Mapped[str] = mapped_column(
        mysql.CHAR(charset="ascii", collation="ascii_bin", length=36),
        nullable=False,
        autoincrement=False,
        comment="稳定UUID",
    )
    title: Mapped[str] = mapped_column(
        mysql.VARCHAR(length=120),
        nullable=False,
        autoincrement=False,
        comment="阶段名称",
    )
    description: Mapped[str | None] = mapped_column(
        mysql.TEXT(),
        nullable=True,
        autoincrement=False,
        comment="阶段说明",
    )
    position: Mapped[int] = mapped_column(
        mysql.INTEGER(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="同路线目录顺序，正整数",
    )
    canvas_x: Mapped[Decimal] = mapped_column(
        mysql.DECIMAL(precision=12, scale=2),
        nullable=False,
        autoincrement=False,
        server_default=text("0"),
        comment="画布横坐标，可为负",
    )
    canvas_y: Mapped[Decimal] = mapped_column(
        mysql.DECIMAL(precision=12, scale=2),
        nullable=False,
        autoincrement=False,
        server_default=text("0"),
        comment="画布纵坐标，可为负",
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


class RoadmapStageEdge(Base):
    """同路线阶段连线，联合外键拒绝跨路线引用。"""

    __tablename__ = "roadmap_stage_edges"
    __table_args__ = (
        UniqueConstraint(
            "roadmap_id", "source_stage_id", "target_stage_id", name="uq_roadmap_stage_edges_1"
        ),
        ForeignKeyConstraint(
            ["roadmap_id"],
            ["skill_roadmaps.id"],
            name="fk_roadmap_stage_edges_1",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["source_stage_id", "roadmap_id"],
            ["roadmap_stages.id", "roadmap_stages.roadmap_id"],
            name="fk_roadmap_stage_edges_2",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["target_stage_id", "roadmap_id"],
            ["roadmap_stages.id", "roadmap_stages.roadmap_id"],
            name="fk_roadmap_stage_edges_3",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        Index("idx_roadmap_stage_edges_1", "roadmap_id", "target_stage_id"),
        Index("idx_roadmap_stage_edges_fk_2", "source_stage_id", "roadmap_id"),
        Index("idx_roadmap_stage_edges_fk_3", "target_stage_id", "roadmap_id"),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=True,
        primary_key=True,
        comment="边标识",
    )
    roadmap_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="所属路线",
    )
    source_stage_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="起点阶段",
    )
    target_stage_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="终点阶段",
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
