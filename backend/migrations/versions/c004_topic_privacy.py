"""独立话题动态隐私，既有账号默认不公开话题活动。"""

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import mysql

revision = "c004_topic_privacy"
down_revision = "c003_official_roadmaps"
branch_labels = None
depends_on = None


def topic_public_column():
    """MySQL8.0.14使用触发器约束布尔值，不依赖CHECK。"""
    return sa.Column(
        "topic_public",
        mysql.TINYINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        server_default=sa.text("0"),
        comment="发布话题动态是否公开",
    )


def upgrade():
    """增量增加独立开关，不修改既有四项选择、账号或业务记录。"""
    op.add_column("user_privacy_settings", topic_public_column())
    for prefix, event in (("bi", "INSERT"), ("bu", "UPDATE")):
        op.execute(
            sa.text(
                f"CREATE TRIGGER {prefix}_user_privacy_settings_topic "
                f"BEFORE {event} ON user_privacy_settings FOR EACH ROW "
                "BEGIN IF NEW.topic_public IS NULL OR NEW.topic_public NOT IN (0,1) THEN "
                "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='invalid topic privacy'; "
                "END IF; END"
            )
        )


def downgrade():
    """已有公开话题选择时禁止静默丢失设置。"""
    if context.is_offline_mode():
        raise RuntimeError("请在线核对话题隐私后降级")
    if (
        op.get_bind()
        .execute(sa.text("SELECT COUNT(*) FROM user_privacy_settings WHERE topic_public<>0"))
        .scalar_one()
    ):
        raise RuntimeError("存在话题公开设置，禁止移除独立隐私字段")
    for prefix in ("bi", "bu"):
        op.execute(sa.text(f"DROP TRIGGER {prefix}_user_privacy_settings_topic"))
    op.drop_column("user_privacy_settings", "topic_public")
