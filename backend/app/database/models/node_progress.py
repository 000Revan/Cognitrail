"""公开社区数据模型：user_node_progress。"""

from datetime import datetime

from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint, text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import TABLE_OPTIONS, Base


class UserNodeProgress(Base):
    """绑定同会话同版本节点的完成事实，独立于每日打卡。"""

    __tablename__ = "user_node_progress"
    __table_args__ = (
        UniqueConstraint("session_id", "release_node_id", name="uq_user_node_progress_1"),
        ForeignKeyConstraint(
            ["release_id"],
            ["roadmap_releases.id"],
            name="fk_user_node_progress_1",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["source_progress_id"],
            ["user_node_progress.id"],
            name="fk_user_node_progress_2",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["session_id", "release_id"],
            ["learning_sessions.id", "learning_sessions.release_id"],
            name="fk_user_node_progress_3",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["release_node_id", "release_id"],
            ["release_nodes.id", "release_nodes.release_id"],
            name="fk_user_node_progress_4",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        Index("idx_user_node_progress_1", "session_id", "is_completed", "release_node_id"),
        Index("idx_user_node_progress_fk_1", "release_id"),
        Index("idx_user_node_progress_fk_2", "source_progress_id"),
        Index("idx_user_node_progress_fk_3", "session_id", "release_id"),
        Index("idx_user_node_progress_fk_4", "release_node_id", "release_id"),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=True,
        primary_key=True,
        comment="进度行ID",
    )
    session_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="所属会话",
    )
    release_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="版本约束冗余键",
    )
    release_node_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="冻结节点",
    )
    is_completed: Mapped[int] = mapped_column(
        mysql.TINYINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        server_default=text("0"),
        comment="0或1，缺行也表示未完成",
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=True,
        autoincrement=False,
        comment="当前完成时间，撤销时清空",
    )
    completion_source: Mapped[str] = mapped_column(
        mysql.VARCHAR(charset="ascii", collation="ascii_bin", length=16),
        nullable=False,
        autoincrement=False,
        server_default=text("'manual'"),
        comment="manual或migrated或confirmed",
    )
    source_progress_id: Mapped[int | None] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=True,
        autoincrement=False,
        comment="迁移来源记录",
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
