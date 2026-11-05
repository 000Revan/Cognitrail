"""公开社区数据模型：skill_roadmaps。"""

from datetime import datetime

from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint, text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import TABLE_OPTIONS, Base


class SkillRoadmap(Base):
    """路线工作稿及当前公开版指针，分发状态与治理状态独立。"""

    __tablename__ = "skill_roadmaps"
    __table_args__ = (
        UniqueConstraint("id", "current_release_id", name="uq_skill_roadmaps_1"),
        ForeignKeyConstraint(
            ["creator_id"],
            ["users.id"],
            name="fk_skill_roadmaps_1",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["current_release_id", "id"],
            ["roadmap_releases.id", "roadmap_releases.roadmap_id"],
            name="fk_skill_roadmaps_2",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        Index("idx_skill_roadmaps_1", "creator_id", "id"),
        Index(
            "idx_skill_roadmaps_2", "distribution_status", "moderation_status", "published_at", "id"
        ),
        Index("idx_skill_roadmaps_fk_2", "current_release_id", "id"),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=True,
        primary_key=True,
        comment="路线标识",
    )
    creator_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="作者",
    )
    title: Mapped[str] = mapped_column(
        mysql.VARCHAR(length=120),
        nullable=False,
        autoincrement=False,
        comment="工作稿标题",
    )
    summary: Mapped[str] = mapped_column(
        mysql.VARCHAR(length=1000),
        nullable=False,
        autoincrement=False,
        server_default=text("''"),
        comment="路线简介，统一描述内容、适合人群、基础要求与预期目标",
    )
    difficulty: Mapped[str] = mapped_column(
        mysql.VARCHAR(charset="ascii", collation="ascii_bin", length=16),
        nullable=False,
        autoincrement=False,
        server_default=text("'beginner'"),
        comment="beginner或intermediate或advanced",
    )
    effort_note: Mapped[str | None] = mapped_column(
        mysql.VARCHAR(length=200),
        nullable=True,
        autoincrement=False,
        comment="选填参考投入时间；空白保存NULL且不显示，填写时注明仅供参考",
    )
    license_code: Mapped[str] = mapped_column(
        mysql.VARCHAR(length=64),
        nullable=False,
        autoincrement=False,
        server_default=text("'UNSPECIFIED'"),
        comment="路线内容许可标识",
    )
    license_url: Mapped[str | None] = mapped_column(
        mysql.VARCHAR(length=2048),
        nullable=True,
        autoincrement=False,
        comment="自定义许可地址",
    )
    current_release_id: Mapped[int | None] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=True,
        autoincrement=False,
        comment="当前公开版本指针",
    )
    edit_version: Mapped[int] = mapped_column(
        mysql.INTEGER(unsigned=True),
        nullable=False,
        autoincrement=False,
        server_default=text("1"),
        comment="工作稿乐观锁，正整数",
    )
    distribution_status: Mapped[str] = mapped_column(
        mysql.VARCHAR(charset="ascii", collation="ascii_bin", length=16),
        nullable=False,
        autoincrement=False,
        server_default=text("'draft'"),
        comment="draft或published或archived",
    )
    moderation_status: Mapped[str] = mapped_column(
        mysql.VARCHAR(charset="ascii", collation="ascii_bin", length=16),
        nullable=False,
        autoincrement=False,
        server_default=text("'normal'"),
        comment="normal或disabled",
    )
    author_archived_at: Mapped[datetime | None] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=True,
        autoincrement=False,
        comment="作者归档时间",
    )
    published_at: Mapped[datetime | None] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=True,
        autoincrement=False,
        comment="最近发布时刻",
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
    roadmap_type: Mapped[str] = mapped_column(
        mysql.ENUM("user", "official"),
        nullable=False,
        server_default=text("'user'"),
        comment="user社区路线或official官方路线",
    )
