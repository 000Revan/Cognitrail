"""增加按学习会话隔离的外部资源访问记录，不回填既有资源状态。"""

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import mysql

revision = "c005_resource_visits"
down_revision = "c004_topic_privacy"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "resource_visits",
        sa.Column("session_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("release_resource_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("release_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("first_visited_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("last_visited_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("session_id", "release_resource_id"),
        sa.ForeignKeyConstraint(
            ["session_id", "release_id"],
            ["learning_sessions.id", "learning_sessions.release_id"],
            name="fk_resource_visits_session",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "release_resource_id"],
            ["release_resources.release_id", "release_resources.id"],
            name="fk_resource_visits_resource",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("idx_resource_visits_session", "resource_visits", ["session_id", "release_id"])
    op.create_index(
        "idx_resource_visits_resource", "resource_visits", ["release_id", "release_resource_id"]
    )


def downgrade():
    if context.is_offline_mode():
        raise RuntimeError("请在线核对访问记录后降级")
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM resource_visits")).scalar_one():
        raise RuntimeError("存在资源访问记录，禁止自动丢失数据")
    op.drop_table("resource_visits")
