"""公开社区数据模型：activity_events。"""

from datetime import date, datetime

from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint, text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import TABLE_OPTIONS, Base


class ActivityEvent(Base):
    """活动来源事实，公开查询仍需校验当前分类隐私与目标可见性。"""

    __tablename__ = "activity_events"
    __table_args__ = (
        UniqueConstraint("event_key", name="uq_activity_events_1"),
        ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name="fk_activity_events_1",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["roadmap_id"],
            ["skill_roadmaps.id"],
            name="fk_activity_events_2",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["checkin_id"],
            ["roadmap_checkins.id"],
            name="fk_activity_events_3",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["release_id", "roadmap_id"],
            ["roadmap_releases.id", "roadmap_releases.roadmap_id"],
            name="fk_activity_events_4",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        Index("idx_activity_events_1", "actor_id", "created_at", "id"),
        Index("idx_activity_events_2", "actor_id", "activity_type", "occurred_on", "id"),
        Index("idx_activity_events_fk_2", "roadmap_id"),
        Index("idx_activity_events_fk_3", "checkin_id"),
        Index("idx_activity_events_fk_4", "release_id", "roadmap_id"),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=True,
        primary_key=True,
        comment="活动ID",
    )
    actor_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="行为人",
    )
    activity_type: Mapped[str] = mapped_column(
        mysql.VARCHAR(charset="ascii", collation="ascii_bin", length=16),
        nullable=False,
        autoincrement=False,
        comment="publish或checkin或favorite或learning",
    )
    roadmap_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="活动涉及路线",
    )
    release_id: Mapped[int | None] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=True,
        autoincrement=False,
        comment="发布更新版本",
    )
    checkin_id: Mapped[int | None] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=True,
        autoincrement=False,
        comment="打卡来源",
    )
    event_key: Mapped[str] = mapped_column(
        mysql.VARCHAR(charset="ascii", collation="ascii_bin", length=120),
        nullable=False,
        autoincrement=False,
        comment="事实事件幂等标识",
    )
    visibility: Mapped[str] = mapped_column(
        mysql.VARCHAR(charset="ascii", collation="ascii_bin", length=16),
        nullable=False,
        autoincrement=False,
        server_default=text("'public'"),
        comment="public或private，分类设置仍需共同判断",
    )
    is_active: Mapped[int] = mapped_column(
        mysql.TINYINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        server_default=text("1"),
        comment="取消收藏、退出学习等使活动失效",
    )
    occurred_on: Mapped[date] = mapped_column(
        mysql.DATE(),
        nullable=False,
        autoincrement=False,
        comment="事件业务日期，用于打卡聚合",
    )
    created_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=False,
        autoincrement=False,
        server_default=text("CURRENT_TIMESTAMP(6)"),
        comment="发生时间",
    )
