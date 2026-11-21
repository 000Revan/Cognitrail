"""增加助手会话与最终消息；SQLite 检查点由官方 saver 独立管理。"""

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import mysql

revision = "c006_agent_history"
down_revision = "c005_resource_visits"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_conversations",
        sa.Column("id", mysql.CHAR(36, charset="ascii", collation="ascii_bin"), nullable=False),
        sa.Column("user_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("title", mysql.VARCHAR(100), nullable=False),
        sa.Column(
            "last_checkpoint_id",
            mysql.VARCHAR(100, charset="ascii", collation="ascii_bin"),
            nullable=True,
            comment="最近成功的主图检查点；首次请求运行前保存空基线",
        ),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_agent_conversations_user",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index(
        "idx_agent_conversations_user_updated",
        "agent_conversations",
        ["user_id", "updated_at", "id"],
    )
    op.create_table(
        "agent_messages",
        sa.Column("id", mysql.CHAR(36, charset="ascii", collation="ascii_bin"), nullable=False),
        sa.Column(
            "conversation_id",
            mysql.CHAR(36, charset="ascii", collation="ascii_bin"),
            nullable=False,
        ),
        sa.Column("position", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("role", mysql.ENUM("user", "assistant"), nullable=False),
        sa.Column("content", mysql.MEDIUMTEXT(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "position", name="uq_agent_messages_position"),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["agent_conversations.id"],
            name="fk_agent_messages_conversation",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )


def downgrade():
    """已有会话时拒绝自动删除历史，与现有增量迁移保持一致。"""
    if context.is_offline_mode():
        raise RuntimeError("请在线核对助手会话后降级")
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM agent_conversations")).scalar_one():
        raise RuntimeError("存在助手会话，禁止自动丢失数据")
    op.drop_table("agent_messages")
    op.drop_table("agent_conversations")
