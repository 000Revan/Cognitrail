"""公开社区数据模型：content_reports, moderation_actions, audit_logs。"""

from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKeyConstraint, Index, text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import TABLE_OPTIONS, Base


class ContentReport(Base):
    """单目标举报及处理结果，不公开举报人身份。"""

    __tablename__ = "content_reports"
    __table_args__ = (
        ForeignKeyConstraint(
            ["reporter_id"],
            ["users.id"],
            name="fk_content_reports_1",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["roadmap_id"],
            ["skill_roadmaps.id"],
            name="fk_content_reports_2",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["issue_id"],
            ["roadmap_issues.id"],
            name="fk_content_reports_3",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["comment_id"],
            ["issue_comments.id"],
            name="fk_content_reports_4",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["handled_by"],
            ["users.id"],
            name="fk_content_reports_5",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        Index("idx_content_reports_1", "status", "created_at", "id"),
        Index("idx_content_reports_2", "reporter_id", "created_at", "id"),
        Index("idx_content_reports_fk_2", "roadmap_id"),
        Index("idx_content_reports_fk_3", "issue_id"),
        Index("idx_content_reports_fk_4", "comment_id"),
        Index("idx_content_reports_fk_5", "handled_by"),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=True,
        primary_key=True,
        comment="举报ID",
    )
    reporter_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="举报人，非公开资料",
    )
    roadmap_id: Mapped[int | None] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=True,
        autoincrement=False,
        comment="路线举报目标",
    )
    issue_id: Mapped[int | None] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=True,
        autoincrement=False,
        comment="主题举报目标",
    )
    comment_id: Mapped[int | None] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=True,
        autoincrement=False,
        comment="评论举报目标",
    )
    reason_code: Mapped[str] = mapped_column(
        mysql.VARCHAR(length=32),
        nullable=False,
        autoincrement=False,
        comment="垃圾广告、侵权、违规等受控原因码",
    )
    description: Mapped[str] = mapped_column(
        mysql.VARCHAR(length=2000),
        nullable=False,
        autoincrement=False,
        server_default=text("''"),
        comment="补充描述",
    )
    status: Mapped[str] = mapped_column(
        mysql.VARCHAR(charset="ascii", collation="ascii_bin", length=16),
        nullable=False,
        autoincrement=False,
        server_default=text("'pending'"),
        comment="pending或processing或resolved或rejected",
    )
    handled_by: Mapped[int | None] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=True,
        autoincrement=False,
        comment="处理管理员",
    )
    handled_at: Mapped[datetime | None] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=True,
        autoincrement=False,
        comment="结案时间",
    )
    result_note: Mapped[str | None] = mapped_column(
        mysql.VARCHAR(length=1000),
        nullable=True,
        autoincrement=False,
        comment="处理结论，向举报人展示时脱敏",
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


class ModerationAction(Base):
    """治理操作与前后状态证据，不级联删除学习事实。"""

    __tablename__ = "moderation_actions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name="fk_moderation_actions_1",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["report_id"],
            ["content_reports.id"],
            name="fk_moderation_actions_2",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        Index("idx_moderation_actions_1", "target_type", "target_id", "created_at", "id"),
        Index("idx_moderation_actions_2", "actor_id", "created_at", "id"),
        Index("idx_moderation_actions_fk_2", "report_id"),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=True,
        primary_key=True,
        comment="治理记录ID",
    )
    actor_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="管理操作者",
    )
    report_id: Mapped[int | None] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=True,
        autoincrement=False,
        comment="来源举报",
    )
    target_type: Mapped[str] = mapped_column(
        mysql.VARCHAR(charset="ascii", collation="ascii_bin", length=24),
        nullable=False,
        autoincrement=False,
        comment="user或roadmap或release或issue或comment或checkin",
    )
    target_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="多态目标，SERVICE验证存在",
    )
    action: Mapped[str] = mapped_column(
        mysql.VARCHAR(charset="ascii", collation="ascii_bin", length=24),
        nullable=False,
        autoincrement=False,
        comment="disable或restore或hide或invalidate",
    )
    reason: Mapped[str] = mapped_column(
        mysql.VARCHAR(length=1000),
        nullable=False,
        autoincrement=False,
        comment="处理原因",
    )
    before_state: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(
        mysql.JSON(),
        nullable=True,
        autoincrement=False,
        comment="必要的原控制状态，不复制正文",
    )
    after_state: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(
        mysql.JSON(),
        nullable=True,
        autoincrement=False,
        comment="新的控制状态",
    )
    created_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=False,
        autoincrement=False,
        server_default=text("CURRENT_TIMESTAMP(6)"),
        comment="处理时间",
    )


class AuditLog(Base):
    """必要操作审计，不记录密码、令牌或私密正文。"""

    __tablename__ = "audit_logs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name="fk_audit_logs_1",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        Index("idx_audit_logs_1", "request_id"),
        Index("idx_audit_logs_2", "target_type", "target_id", "created_at", "id"),
        Index("idx_audit_logs_3", "actor_id", "created_at", "id"),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=True,
        primary_key=True,
        comment="审计ID",
    )
    actor_id: Mapped[int | None] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=True,
        autoincrement=False,
        comment="操作者，系统任务可空",
    )
    action_code: Mapped[str] = mapped_column(
        mysql.VARCHAR(length=64),
        nullable=False,
        autoincrement=False,
        comment="受控操作编码",
    )
    target_type: Mapped[str] = mapped_column(
        mysql.VARCHAR(length=32),
        nullable=False,
        autoincrement=False,
        comment="对象类型",
    )
    target_id: Mapped[int | None] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=True,
        autoincrement=False,
        comment="对象标识，多态引用",
    )
    request_id: Mapped[str] = mapped_column(
        mysql.VARCHAR(charset="ascii", collation="ascii_bin", length=64),
        nullable=False,
        autoincrement=False,
        comment="请求追踪ID",
    )
    result: Mapped[str] = mapped_column(
        mysql.VARCHAR(charset="ascii", collation="ascii_bin", length=16),
        nullable=False,
        autoincrement=False,
        comment="success或failure",
    )
    details: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(
        mysql.JSON(),
        nullable=True,
        autoincrement=False,
        comment="必要上下文，不含密码令牌或私密正文",
    )
    created_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=False,
        autoincrement=False,
        server_default=text("CURRENT_TIMESTAMP(6)"),
        comment="事件时间",
    )
