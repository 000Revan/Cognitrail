"""独立官方路线归属，已有路线保持社区类型。"""

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import mysql

revision = "c003_official_roadmaps"
down_revision = "c002_notification_delete"
branch_labels = None
depends_on = None


def roadmap_type_column():
    """冻结归属字段；ENUM在MySQL8.0.14直接约束合法值。"""
    return sa.Column(
        "roadmap_type",
        mysql.ENUM("user", "official"),
        nullable=False,
        server_default=sa.text("'user'"),
        comment="user社区路线或official官方路线",
    )


def upgrade():
    """只增加类型，既有路线和发布快照保持原样。"""
    op.add_column("skill_roadmaps", roadmap_type_column())


def downgrade():
    """存在官方路线时拒绝丢失归属信息的回退。"""
    if context.is_offline_mode():
        raise RuntimeError("请在线核对官方路线后降级")
    if (
        op.get_bind()
        .execute(sa.text("SELECT COUNT(*) FROM skill_roadmaps WHERE roadmap_type='official'"))
        .scalar_one()
    ):
        raise RuntimeError("存在官方路线，禁止移除归属字段")
    op.drop_column("skill_roadmaps", "roadmap_type")
