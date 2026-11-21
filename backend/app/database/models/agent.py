"""助手会话和最终展示消息；运行状态由 SQLite checkpointer 管理。"""

from datetime import datetime

from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import TABLE_OPTIONS, Base


class AgentConversation(Base):
    """用户会话及最近正式保存成功的主图检查点。"""

    __tablename__ = "agent_conversations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_agent_conversations_user",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        Index("idx_agent_conversations_user_updated", "user_id", "updated_at", "id"),
        TABLE_OPTIONS,
    )

    id: Mapped[str] = mapped_column(
        mysql.CHAR(36, charset="ascii", collation="ascii_bin"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(mysql.BIGINT(unsigned=True), nullable=False)
    title: Mapped[str] = mapped_column(mysql.VARCHAR(100), nullable=False)
    last_checkpoint_id: Mapped[str | None] = mapped_column(
        mysql.VARCHAR(100, charset="ascii", collation="ascii_bin"),
        comment="最近成功的主图检查点；首次请求运行前保存空基线",
    )
    created_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)


class AgentMessage(Base):
    """只保存成功轮次的用户问题和最终回答，按 position 排序。"""

    __tablename__ = "agent_messages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["conversation_id"],
            ["agent_conversations.id"],
            name="fk_agent_messages_conversation",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        UniqueConstraint("conversation_id", "position", name="uq_agent_messages_position"),
        TABLE_OPTIONS,
    )

    id: Mapped[str] = mapped_column(
        mysql.CHAR(36, charset="ascii", collation="ascii_bin"), primary_key=True
    )
    conversation_id: Mapped[str] = mapped_column(
        mysql.CHAR(36, charset="ascii", collation="ascii_bin"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(mysql.INTEGER(unsigned=True), nullable=False)
    role: Mapped[str] = mapped_column(mysql.ENUM("user", "assistant"), nullable=False)
    content: Mapped[str] = mapped_column(mysql.MEDIUMTEXT(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
