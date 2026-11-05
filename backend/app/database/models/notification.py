"""公开社区数据模型：notification_outbox, notifications。"""

from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint, text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import TABLE_OPTIONS, Base


class NotificationOutbox(Base):
    """业务事务产生的可靠通知任务，租约领取和重试由服务层处理。"""

    __tablename__ = "notification_outbox"
    __table_args__ = (
        UniqueConstraint("event_key", name="uq_notification_outbox_1"),
        Index("idx_notification_outbox_1", "status", "available_at", "id"),
        Index("idx_notification_outbox_2", "status", "lease_until", "id"),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=True,
        primary_key=True,
        comment="任务ID",
    )
    event_key: Mapped[str] = mapped_column(
        mysql.VARCHAR(charset="ascii", collation="ascii_bin", length=120),
        nullable=False,
        autoincrement=False,
        comment="领域事件唯一键",
    )
    event_type: Mapped[str] = mapped_column(
        mysql.VARCHAR(length=32),
        nullable=False,
        autoincrement=False,
        comment="issue_created、comment_created、issue_state_changed、release_published、moderation_notice",
    )
    payload: Mapped[dict[str, Any] | list[Any]] = mapped_column(
        mysql.JSON(),
        nullable=False,
        autoincrement=False,
        comment="仅存对象ID及事件必要参数，不复制私密正文",
    )
    status: Mapped[str] = mapped_column(
        mysql.VARCHAR(charset="ascii", collation="ascii_bin", length=16),
        nullable=False,
        autoincrement=False,
        server_default=text("'pending'"),
        comment="pending或processing或done或failed",
    )
    attempts: Mapped[int] = mapped_column(
        mysql.INTEGER(unsigned=True),
        nullable=False,
        autoincrement=False,
        server_default=text("0"),
        comment="已尝试次数",
    )
    available_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=False,
        autoincrement=False,
        comment="下次可执行时间",
    )
    lease_until: Mapped[datetime | None] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=True,
        autoincrement=False,
        comment="处理租约截止，崩溃后可重领",
    )
    lease_token: Mapped[str | None] = mapped_column(
        mysql.CHAR(charset="ascii", collation="ascii_bin", length=36),
        nullable=True,
        autoincrement=False,
        comment="任务认领令牌，防止过期工作进程提交",
    )
    last_error: Mapped[str | None] = mapped_column(
        mysql.VARCHAR(length=1000),
        nullable=True,
        autoincrement=False,
        comment="脱敏后的错误摘要",
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


class Notification(Base):
    """接收者与事件键唯一的站内通知，不存讨论私密正文。"""

    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("recipient_id", "event_key", name="uq_notifications_1"),
        ForeignKeyConstraint(
            ["recipient_id"],
            ["users.id"],
            name="fk_notifications_1",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name="fk_notifications_2",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["roadmap_id"],
            ["skill_roadmaps.id"],
            name="fk_notifications_3",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["issue_id"],
            ["roadmap_issues.id"],
            name="fk_notifications_4",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["release_id", "roadmap_id"],
            ["roadmap_releases.id", "roadmap_releases.roadmap_id"],
            name="fk_notifications_5",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["comment_id", "issue_id"],
            ["issue_comments.id", "issue_comments.issue_id"],
            name="fk_notifications_6",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        Index("idx_notifications_1", "recipient_id", "read_at", "id"),
        Index("idx_notifications_2", "recipient_id", "created_at", "id"),
        Index("idx_notifications_fk_2", "actor_id"),
        Index("idx_notifications_fk_3", "roadmap_id"),
        Index("idx_notifications_fk_4", "issue_id"),
        Index("idx_notifications_fk_5", "release_id", "roadmap_id"),
        Index("idx_notifications_fk_6", "comment_id", "issue_id"),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=True,
        primary_key=True,
        comment="通知ID",
    )
    recipient_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="接收者",
    )
    actor_id: Mapped[int | None] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=True,
        autoincrement=False,
        comment="行为人，系统消息可空",
    )
    notification_type: Mapped[str] = mapped_column(
        mysql.VARCHAR(length=32),
        nullable=False,
        autoincrement=False,
        comment="与outbox事件类型一致",
    )
    event_key: Mapped[str] = mapped_column(
        mysql.VARCHAR(charset="ascii", collation="ascii_bin", length=120),
        nullable=False,
        autoincrement=False,
        comment="来源事件幂等键",
    )
    roadmap_id: Mapped[int | None] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=True,
        autoincrement=False,
        comment="路线目标",
    )
    issue_id: Mapped[int | None] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=True,
        autoincrement=False,
        comment="主题目标",
    )
    comment_id: Mapped[int | None] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=True,
        autoincrement=False,
        comment="回复锚点",
    )
    release_id: Mapped[int | None] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=True,
        autoincrement=False,
        comment="版本目标",
    )
    system_message: Mapped[str | None] = mapped_column(
        mysql.VARCHAR(length=500),
        nullable=True,
        autoincrement=False,
        comment="仅治理说明等系统文本，不存讨论正文",
    )
    read_at: Mapped[datetime | None] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=True,
        autoincrement=False,
        comment="NULL表示未读",
    )
    created_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=False,
        autoincrement=False,
        server_default=text("CURRENT_TIMESTAMP(6)"),
        comment="创建时间",
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=True,
        autoincrement=False,
        comment="收件人删除时间 UTC；保留事件去重记录",
    )
