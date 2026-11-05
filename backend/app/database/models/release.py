"""路线发布快照及冻结阶段、节点、资源和连线。"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint, text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import TABLE_OPTIONS, Base


class RoadmapRelease(Base):
    """完整共享发布快照，幂等来源版本与治理访问状态独立。"""

    __tablename__ = "roadmap_releases"
    __table_args__ = (
        UniqueConstraint("roadmap_id", "version_no", name="uq_roadmap_releases_1"),
        UniqueConstraint("roadmap_id", "source_edit_version", name="uq_roadmap_releases_2"),
        UniqueConstraint("id", "roadmap_id", name="uq_roadmap_releases_3"),
        ForeignKeyConstraint(
            ["roadmap_id"],
            ["skill_roadmaps.id"],
            name="fk_roadmap_releases_1",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["published_by"],
            ["users.id"],
            name="fk_roadmap_releases_2",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        Index("idx_roadmap_releases_1", "roadmap_id", "published_at", "id"),
        Index("idx_roadmap_releases_fk_2", "published_by"),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=True,
        primary_key=True,
        comment="发布版本ID",
    )
    roadmap_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="所属路线",
    )
    version_no: Mapped[int] = mapped_column(
        mysql.INTEGER(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="路线内版本序号，正整数",
    )
    source_edit_version: Mapped[int] = mapped_column(
        mysql.INTEGER(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="产生版本的工作稿修订号",
    )
    title: Mapped[str] = mapped_column(
        mysql.VARCHAR(length=120),
        nullable=False,
        autoincrement=False,
        comment="标题快照",
    )
    summary: Mapped[str] = mapped_column(
        mysql.VARCHAR(length=1000),
        nullable=False,
        autoincrement=False,
        comment="完整简介快照，保留作者描述的适合人群、基础要求与预期目标",
    )
    difficulty: Mapped[str] = mapped_column(
        mysql.VARCHAR(charset="ascii", collation="ascii_bin", length=16),
        nullable=False,
        autoincrement=False,
        comment="难度快照，同工作稿枚举",
    )
    effort_note: Mapped[str | None] = mapped_column(
        mysql.VARCHAR(length=200),
        nullable=True,
        autoincrement=False,
        comment="可选参考投入时间快照；NULL不显示，填写时注明仅供参考",
    )
    license_code: Mapped[str] = mapped_column(
        mysql.VARCHAR(length=64),
        nullable=False,
        autoincrement=False,
        comment="许可快照",
    )
    license_url: Mapped[str | None] = mapped_column(
        mysql.VARCHAR(length=2048),
        nullable=True,
        autoincrement=False,
        comment="许可地址快照",
    )
    update_summary: Mapped[str] = mapped_column(
        mysql.VARCHAR(length=2000),
        nullable=False,
        autoincrement=False,
        comment="本次更新说明，首次发布说明亦填写",
    )
    content_hash: Mapped[str] = mapped_column(
        mysql.CHAR(charset="ascii", collation="ascii_bin", length=64),
        nullable=False,
        autoincrement=False,
        comment="规范化快照SHA256，含结构资源，不含发布时间",
    )
    published_by: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="实际发布操作者",
    )
    published_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=False,
        autoincrement=False,
        comment="发布时刻",
    )
    content_access: Mapped[str] = mapped_column(
        mysql.VARCHAR(charset="ascii", collation="ascii_bin", length=16),
        nullable=False,
        autoincrement=False,
        server_default=text("'normal'"),
        comment="normal或restricted，治理字段",
    )


class ReleaseStage(Base):
    """冻结阶段顺序与稳定身份，不引用可变工作稿。"""

    __tablename__ = "release_stages"
    __table_args__ = (
        UniqueConstraint("id", "release_id", name="uq_release_stages_1"),
        UniqueConstraint("release_id", "stable_key", name="uq_release_stages_2"),
        UniqueConstraint("release_id", "position", name="uq_release_stages_3"),
        ForeignKeyConstraint(
            ["release_id"],
            ["roadmap_releases.id"],
            name="fk_release_stages_1",
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
        comment="冻结阶段ID",
    )
    release_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="所属版本",
    )
    stable_key: Mapped[str] = mapped_column(
        mysql.CHAR(charset="ascii", collation="ascii_bin", length=36),
        nullable=False,
        autoincrement=False,
        comment="工作稿稳定身份副本",
    )
    title: Mapped[str] = mapped_column(
        mysql.VARCHAR(length=120),
        nullable=False,
        autoincrement=False,
        comment="标题快照",
    )
    description: Mapped[str | None] = mapped_column(
        mysql.TEXT(),
        nullable=True,
        autoincrement=False,
        comment="说明快照",
    )
    position: Mapped[int] = mapped_column(
        mysql.INTEGER(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="版本内阶段顺序，正整数",
    )
    canvas_x: Mapped[Decimal] = mapped_column(
        mysql.DECIMAL(precision=12, scale=2),
        nullable=False,
        autoincrement=False,
        comment="横坐标快照",
    )
    canvas_y: Mapped[Decimal] = mapped_column(
        mysql.DECIMAL(precision=12, scale=2),
        nullable=False,
        autoincrement=False,
        comment="纵坐标快照",
    )


class ReleaseNode(Base):
    """冻结学习语义、参考分钟、可选属性及进度计入规则。"""

    __tablename__ = "release_nodes"
    __table_args__ = (
        UniqueConstraint("id", "release_id", name="uq_release_nodes_1"),
        UniqueConstraint("release_id", "stable_key", name="uq_release_nodes_2"),
        UniqueConstraint("stage_id", "position", name="uq_release_nodes_3"),
        ForeignKeyConstraint(
            ["release_id"],
            ["roadmap_releases.id"],
            name="fk_release_nodes_1",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["stage_id", "release_id"],
            ["release_stages.id", "release_stages.release_id"],
            name="fk_release_nodes_2",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        Index("idx_release_nodes_1", "release_id", "counts_toward_progress", "id"),
        Index("idx_release_nodes_fk_2", "stage_id", "release_id"),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=True,
        primary_key=True,
        comment="冻结节点ID",
    )
    release_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="所属版本",
    )
    stage_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="所属冻结阶段",
    )
    stable_key: Mapped[str] = mapped_column(
        mysql.CHAR(charset="ascii", collation="ascii_bin", length=36),
        nullable=False,
        autoincrement=False,
        comment="跨版本任务身份",
    )
    title: Mapped[str] = mapped_column(
        mysql.VARCHAR(length=150),
        nullable=False,
        autoincrement=False,
        comment="标题快照",
    )
    content: Mapped[str | None] = mapped_column(
        mysql.MEDIUMTEXT(),
        nullable=True,
        autoincrement=False,
        comment="正文快照",
    )
    tips: Mapped[str | None] = mapped_column(
        mysql.TEXT(),
        nullable=True,
        autoincrement=False,
        comment="提示快照",
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
        comment="拓展标记，0或1",
    )
    counts_toward_progress: Mapped[int] = mapped_column(
        mysql.TINYINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="是否计入分母，0或1",
    )
    revision_no: Mapped[int] = mapped_column(
        mysql.INTEGER(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="语义修订号，正整数",
    )
    change_policy: Mapped[str] = mapped_column(
        mysql.VARCHAR(charset="ascii", collation="ascii_bin", length=16),
        nullable=False,
        autoincrement=False,
        comment="retain或reconfirm",
    )
    canvas_x: Mapped[Decimal] = mapped_column(
        mysql.DECIMAL(precision=12, scale=2),
        nullable=False,
        autoincrement=False,
        comment="横坐标快照",
    )
    canvas_y: Mapped[Decimal] = mapped_column(
        mysql.DECIMAL(precision=12, scale=2),
        nullable=False,
        autoincrement=False,
        comment="纵坐标快照",
    )
    estimated_minutes: Mapped[int | None] = mapped_column(
        mysql.INTEGER(unsigned=True),
        nullable=True,
        autoincrement=False,
        comment="可选参考分钟快照；NULL不显示，非空须正数并注明仅供参考",
    )


class ReleaseResource(Base):
    """冻结资源引用及访问属性，不托管外站内容。"""

    __tablename__ = "release_resources"
    __table_args__ = (
        UniqueConstraint("node_id", "position", name="uq_release_resources_1"),
        ForeignKeyConstraint(
            ["release_id"],
            ["roadmap_releases.id"],
            name="fk_release_resources_1",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["node_id", "release_id"],
            ["release_nodes.id", "release_nodes.release_id"],
            name="fk_release_resources_2",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        Index("idx_release_resources_1", "release_id", "id"),
        Index("idx_release_resources_fk_2", "node_id", "release_id"),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=True,
        primary_key=True,
        comment="冻结资源ID",
    )
    release_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="所属发布版本",
    )
    node_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="所属冻结节点",
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
        comment="发布时外链地址",
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
        comment="语言快照",
    )
    access_type: Mapped[str] = mapped_column(
        mysql.VARCHAR(charset="ascii", collation="ascii_bin", length=16),
        nullable=False,
        autoincrement=False,
        comment="free或paid或freemium或unknown",
    )
    position: Mapped[int] = mapped_column(
        mysql.INTEGER(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="节点内顺序，正整数",
    )


class ReleaseStageEdge(Base):
    """发布版阶段连线，端点必须属于同一版本。"""

    __tablename__ = "release_stage_edges"
    __table_args__ = (
        UniqueConstraint(
            "release_id", "source_stage_id", "target_stage_id", name="uq_release_stage_edges_1"
        ),
        ForeignKeyConstraint(
            ["release_id"],
            ["roadmap_releases.id"],
            name="fk_release_stage_edges_1",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["source_stage_id", "release_id"],
            ["release_stages.id", "release_stages.release_id"],
            name="fk_release_stage_edges_2",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["target_stage_id", "release_id"],
            ["release_stages.id", "release_stages.release_id"],
            name="fk_release_stage_edges_3",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        Index("idx_release_stage_edges_1", "release_id", "target_stage_id"),
        Index("idx_release_stage_edges_fk_2", "source_stage_id", "release_id"),
        Index("idx_release_stage_edges_fk_3", "target_stage_id", "release_id"),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=True,
        primary_key=True,
        comment="冻结边ID",
    )
    release_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="所属版本",
    )
    source_stage_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="起点冻结阶段",
    )
    target_stage_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="终点冻结阶段",
    )
