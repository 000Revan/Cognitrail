"""公开社区数据模型：user_roadmaps, learning_sessions, learning_session_events。"""

from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint, text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import TABLE_OPTIONS, Base


class UserRoadmap(Base):
    """用户与路线唯一的学习关系，当前会话归属由联合外键保证。"""

    __tablename__ = "user_roadmaps"
    __table_args__ = (
        UniqueConstraint("user_id", "roadmap_id", name="uq_user_roadmaps_1"),
        UniqueConstraint("id", "roadmap_id", name="uq_user_roadmaps_2"),
        ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_roadmaps_1",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["roadmap_id"],
            ["skill_roadmaps.id"],
            name="fk_user_roadmaps_2",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["current_session_id", "id", "roadmap_id"],
            [
                "learning_sessions.id",
                "learning_sessions.user_roadmap_id",
                "learning_sessions.roadmap_id",
            ],
            name="fk_user_roadmaps_3",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["dismissed_release_id", "roadmap_id"],
            ["roadmap_releases.id", "roadmap_releases.roadmap_id"],
            name="fk_user_roadmaps_4",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        Index("idx_user_roadmaps_1", "user_id", "status", "id"),
        Index("idx_user_roadmaps_2", "roadmap_id", "id"),
        Index("idx_user_roadmaps_fk_3", "current_session_id", "id", "roadmap_id"),
        Index("idx_user_roadmaps_fk_4", "dismissed_release_id", "roadmap_id"),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=True,
        primary_key=True,
        comment="学习关系ID",
    )
    user_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="学习者",
    )
    roadmap_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="路线",
    )
    current_session_id: Mapped[int | None] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=True,
        autoincrement=False,
        comment="初始化时暂空，提交前必须有效",
    )
    status: Mapped[str] = mapped_column(
        mysql.VARCHAR(charset="ascii", collation="ascii_bin", length=16),
        nullable=False,
        autoincrement=False,
        server_default=text("'active'"),
        comment="active或abandoned",
    )
    started_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=False,
        autoincrement=False,
        comment="首次加入时间",
    )
    abandoned_at: Mapped[datetime | None] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=True,
        autoincrement=False,
        comment="退出时间",
    )
    dismissed_release_id: Mapped[int | None] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=True,
        autoincrement=False,
        comment="用户已忽略提醒的版本",
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


class LearningSession(Base):
    """绑定发布版的学习会话，保存位置和进度版本，旧会话保留。"""

    __tablename__ = "learning_sessions"
    __table_args__ = (
        UniqueConstraint("user_roadmap_id", "release_id", name="uq_learning_sessions_1"),
        UniqueConstraint("id", "release_id", name="uq_learning_sessions_2"),
        UniqueConstraint("id", "user_roadmap_id", name="uq_learning_sessions_3"),
        UniqueConstraint("id", "user_roadmap_id", "roadmap_id", name="uq_learning_sessions_4"),
        ForeignKeyConstraint(
            ["roadmap_id"],
            ["skill_roadmaps.id"],
            name="fk_learning_sessions_1",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["source_session_id"],
            ["learning_sessions.id"],
            name="fk_learning_sessions_2",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["user_roadmap_id", "roadmap_id"],
            ["user_roadmaps.id", "user_roadmaps.roadmap_id"],
            name="fk_learning_sessions_3",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["release_id", "roadmap_id"],
            ["roadmap_releases.id", "roadmap_releases.roadmap_id"],
            name="fk_learning_sessions_4",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["last_node_id", "release_id"],
            ["release_nodes.id", "release_nodes.release_id"],
            name="fk_learning_sessions_5",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        Index("idx_learning_sessions_1", "user_roadmap_id", "started_at", "id"),
        Index("idx_learning_sessions_fk_1", "roadmap_id"),
        Index("idx_learning_sessions_fk_2", "source_session_id"),
        Index("idx_learning_sessions_fk_3", "user_roadmap_id", "roadmap_id"),
        Index("idx_learning_sessions_fk_4", "release_id", "roadmap_id"),
        Index("idx_learning_sessions_fk_5", "last_node_id", "release_id"),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=True,
        primary_key=True,
        comment="学习会话ID",
    )
    user_roadmap_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="所属学习关系",
    )
    roadmap_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="所属路线",
    )
    release_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="固定发布版本",
    )
    source_session_id: Mapped[int | None] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=True,
        autoincrement=False,
        comment="升级来源；首次加入为空",
    )
    last_node_id: Mapped[int | None] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=True,
        autoincrement=False,
        comment="最后浏览冻结节点",
    )
    last_opened_at: Mapped[datetime | None] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=True,
        autoincrement=False,
        comment="最后浏览时间",
    )
    progress_version: Mapped[int] = mapped_column(
        mysql.INTEGER(unsigned=True),
        nullable=False,
        autoincrement=False,
        server_default=text("1"),
        comment="完成状态或位置变更后递增，防止预览过期",
    )
    started_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=False,
        autoincrement=False,
        comment="该版本开始学习时间",
    )
    first_completed_at: Mapped[datetime | None] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=True,
        autoincrement=False,
        comment="该版本首次全部主线完成时间，不因撤销抹去",
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


class LearningSessionEvent(Base):
    """加入、升级、退出和恢复事件，保留幂等请求键。"""

    __tablename__ = "learning_session_events"
    __table_args__ = (
        UniqueConstraint("user_roadmap_id", "request_key", name="uq_learning_session_events_1"),
        ForeignKeyConstraint(
            ["user_roadmap_id"],
            ["user_roadmaps.id"],
            name="fk_learning_session_events_1",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name="fk_learning_session_events_2",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["from_session_id", "user_roadmap_id"],
            ["learning_sessions.id", "learning_sessions.user_roadmap_id"],
            name="fk_learning_session_events_3",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["to_session_id", "user_roadmap_id"],
            ["learning_sessions.id", "learning_sessions.user_roadmap_id"],
            name="fk_learning_session_events_4",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        Index("idx_learning_session_events_1", "user_roadmap_id", "created_at", "id"),
        Index("idx_learning_session_events_fk_2", "actor_id"),
        Index("idx_learning_session_events_fk_3", "from_session_id", "user_roadmap_id"),
        Index("idx_learning_session_events_fk_4", "to_session_id", "user_roadmap_id"),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=True,
        primary_key=True,
        comment="事件ID",
    )
    user_roadmap_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="所属学习关系",
    )
    actor_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="实际操作用户",
    )
    event_type: Mapped[str] = mapped_column(
        mysql.VARCHAR(charset="ascii", collation="ascii_bin", length=16),
        nullable=False,
        autoincrement=False,
        comment="join或upgrade或abandon或resume",
    )
    from_session_id: Mapped[int | None] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=True,
        autoincrement=False,
        comment="源会话",
    )
    to_session_id: Mapped[int | None] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=True,
        autoincrement=False,
        comment="目标会话",
    )
    request_key: Mapped[str] = mapped_column(
        mysql.VARCHAR(charset="ascii", collation="ascii_bin", length=64),
        nullable=False,
        autoincrement=False,
        comment="操作幂等键",
    )
    details: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(
        mysql.JSON(),
        nullable=True,
        autoincrement=False,
        comment="版本差异摘要与重新确认选择，不存笔记",
    )
    created_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=False,
        autoincrement=False,
        server_default=text("CURRENT_TIMESTAMP(6)"),
        comment="事件发生时间",
    )
