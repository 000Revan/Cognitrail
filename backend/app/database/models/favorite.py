"""公开社区数据模型：roadmap_favorites, roadmap_subscriptions。"""

from datetime import datetime

from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint, text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import TABLE_OPTIONS, Base


class RoadmapFavorite(Base):
    """收藏关系独立于学习关系及更新订阅。"""

    __tablename__ = "roadmap_favorites"
    __table_args__ = (
        UniqueConstraint("user_id", "roadmap_id", name="uq_roadmap_favorites_1"),
        ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_roadmap_favorites_1",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["roadmap_id"],
            ["skill_roadmaps.id"],
            name="fk_roadmap_favorites_2",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        Index("idx_roadmap_favorites_1", "roadmap_id", "id"),
        Index("idx_roadmap_favorites_2", "user_id", "created_at", "id"),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=True,
        primary_key=True,
        comment="收藏标识",
    )
    user_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="收藏人",
    )
    roadmap_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="被收藏路线",
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


class RoadmapSubscription(Base):
    """路线更新订阅，可独立取消，不改变收藏或学习。"""

    __tablename__ = "roadmap_subscriptions"
    __table_args__ = (
        UniqueConstraint("roadmap_id", "user_id", name="uq_roadmap_subscriptions_1"),
        ForeignKeyConstraint(
            ["roadmap_id"],
            ["skill_roadmaps.id"],
            name="fk_roadmap_subscriptions_1",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_roadmap_subscriptions_2",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        Index("idx_roadmap_subscriptions_1", "user_id", "is_subscribed", "id"),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=True,
        primary_key=True,
        comment="订阅ID",
    )
    roadmap_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="被订阅路线",
    )
    user_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="订阅人",
    )
    is_subscribed: Mapped[int] = mapped_column(
        mysql.TINYINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        server_default=text("1"),
        comment="是否订阅新版本",
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
