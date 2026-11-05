"""公开社区数据模型：roadmap_checkins。"""

from datetime import date, datetime

from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint, text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import TABLE_OPTIONS, Base


class RoadmapCheckin(Base):
    """同学习关系同日期唯一的打卡事实，无笔记、收获或时长。"""

    __tablename__ = "roadmap_checkins"
    __table_args__ = (
        UniqueConstraint("user_roadmap_id", "checkin_date", name="uq_roadmap_checkins_1"),
        ForeignKeyConstraint(
            ["user_roadmap_id"],
            ["user_roadmaps.id"],
            name="fk_roadmap_checkins_1",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["invalidated_by"],
            ["users.id"],
            name="fk_roadmap_checkins_2",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["session_id", "user_roadmap_id"],
            ["learning_sessions.id", "learning_sessions.user_roadmap_id"],
            name="fk_roadmap_checkins_3",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        Index("idx_roadmap_checkins_1", "checkin_date", "is_valid", "id"),
        Index("idx_roadmap_checkins_fk_2", "invalidated_by"),
        Index("idx_roadmap_checkins_fk_3", "session_id", "user_roadmap_id"),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=True,
        primary_key=True,
        comment="打卡ID",
    )
    user_roadmap_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="用户路线关系",
    )
    session_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="打卡时学习版本会话",
    )
    checkin_date: Mapped[date] = mapped_column(
        mysql.DATE(),
        nullable=False,
        autoincrement=False,
        comment="统一业务时区自然日",
    )
    timezone_name: Mapped[str] = mapped_column(
        mysql.VARCHAR(length=64),
        nullable=False,
        autoincrement=False,
        server_default=text("'Asia/Shanghai'"),
        comment="日期口径快照",
    )
    is_valid: Mapped[int] = mapped_column(
        mysql.TINYINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        server_default=text("1"),
        comment="治理撤销设0",
    )
    invalidated_at: Mapped[datetime | None] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=True,
        autoincrement=False,
        comment="撤销时间",
    )
    invalidated_by: Mapped[int | None] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=True,
        autoincrement=False,
        comment="治理操作者",
    )
    created_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=False,
        autoincrement=False,
        server_default=text("CURRENT_TIMESTAMP(6)"),
        comment="打卡实际发生时间 UTC",
    )


class StudyRecord:
    """旧接口导入占位；不映射旧表，不能替代新打卡模型。"""

    def __init__(self, **_values) -> None:
        """阻止旧服务误用；新方向使用RoadmapCheckin及独立学习会话。"""
        raise RuntimeError("study_records模型已退役，旧学习服务须按R05适配")
