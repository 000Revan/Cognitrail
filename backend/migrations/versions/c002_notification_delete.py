"""通知收件箱软删除，保留事件去重身份，避免重试后重新出现。"""

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import mysql

revision = "c002_notification_delete"
down_revision = "c001_community"
branch_labels = None
depends_on = None


def deleted_at_column():
    """冻结新增列定义，独立于当前ORM。"""
    return sa.Column(
        "deleted_at",
        mysql.DATETIME(fsp=6),
        nullable=True,
        autoincrement=False,
        comment="收件人删除时间 UTC；保留事件去重记录",
    )


def upgrade():
    """仅增加可空字段，已有消息默认仍可见，不改写通知及业务目标。"""
    op.add_column("notifications", deleted_at_column())


def downgrade():
    """存在删除记录时拒绝降级，避免历史消息意外恢复。"""
    if context.is_offline_mode():
        raise RuntimeError("请在线核对删除记录后降级，禁止离线生成有损回退SQL")
    deleted = (
        op.get_bind()
        .execute(sa.text("SELECT COUNT(*) FROM notifications WHERE deleted_at IS NOT NULL"))
        .scalar_one()
    )
    if deleted:
        raise RuntimeError("存在已删除消息，降级会使消息重新出现；未执行降级")
    op.drop_column("notifications", "deleted_at")
