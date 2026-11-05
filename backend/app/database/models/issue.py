"""公开社区数据模型：roadmap_issues, issue_comments, issue_subscriptions, issue_events。"""

from datetime import datetime

from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint, text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import TABLE_OPTIONS, Base


class RoadmapIssue(Base):
    """路线话题，不绑定节点、版本或问题类型。"""

    __tablename__ = "roadmap_issues"
    __table_args__ = (
        UniqueConstraint("id", "roadmap_id", name="uq_roadmap_issues_1"),
        ForeignKeyConstraint(
            ["roadmap_id"],
            ["skill_roadmaps.id"],
            name="fk_roadmap_issues_1",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name="fk_roadmap_issues_2",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["state_changed_by"],
            ["users.id"],
            name="fk_roadmap_issues_3",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        Index(
            "idx_roadmap_issues_1", "roadmap_id", "visibility", "status", "last_activity_at", "id"
        ),
        Index("idx_roadmap_issues_2", "author_id", "created_at", "id"),
        Index("idx_roadmap_issues_fk_3", "state_changed_by"),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=True,
        primary_key=True,
        comment="主题ID",
    )
    roadmap_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="所属路线",
    )
    author_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="提问者",
    )
    title: Mapped[str] = mapped_column(
        mysql.VARCHAR(length=150),
        nullable=False,
        autoincrement=False,
        comment="用户自由填写的话题标题",
    )
    body: Mapped[str] = mapped_column(
        mysql.MEDIUMTEXT(),
        nullable=False,
        autoincrement=False,
        comment="话题正文，受限Markdown；可自行描述位置或粘贴相关链接",
    )
    status: Mapped[str] = mapped_column(
        mysql.VARCHAR(charset="ascii", collation="ascii_bin", length=16),
        nullable=False,
        autoincrement=False,
        server_default=text("'open'"),
        comment="open或resolved或closed",
    )
    visibility: Mapped[str] = mapped_column(
        mysql.VARCHAR(charset="ascii", collation="ascii_bin", length=16),
        nullable=False,
        autoincrement=False,
        server_default=text("'public'"),
        comment="public或hidden或deleted",
    )
    state_reason: Mapped[str | None] = mapped_column(
        mysql.VARCHAR(length=500),
        nullable=True,
        autoincrement=False,
        comment="最近状态处理原因",
    )
    state_changed_by: Mapped[int | None] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=True,
        autoincrement=False,
        comment="最近状态操作者",
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=False,
        autoincrement=False,
        comment="最近有效回复或状态变更时间",
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


class IssueComment(Base):
    """平铺回复及同话题引用，删除后保留占位身份。"""

    __tablename__ = "issue_comments"
    __table_args__ = (
        UniqueConstraint("id", "issue_id", name="uq_issue_comments_1"),
        ForeignKeyConstraint(
            ["issue_id"],
            ["roadmap_issues.id"],
            name="fk_issue_comments_1",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name="fk_issue_comments_2",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["reply_to_comment_id", "issue_id"],
            ["issue_comments.id", "issue_comments.issue_id"],
            name="fk_issue_comments_3",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        Index("idx_issue_comments_1", "issue_id", "created_at", "id"),
        Index("idx_issue_comments_2", "author_id", "created_at", "id"),
        Index("idx_issue_comments_fk_3", "reply_to_comment_id", "issue_id"),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=True,
        primary_key=True,
        comment="回复ID",
    )
    issue_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="所属主题",
    )
    author_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="回复人",
    )
    reply_to_comment_id: Mapped[int | None] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=True,
        autoincrement=False,
        comment="被回复评论，可空",
    )
    body: Mapped[str] = mapped_column(
        mysql.MEDIUMTEXT(),
        nullable=False,
        autoincrement=False,
        comment="回复正文",
    )
    visibility: Mapped[str] = mapped_column(
        mysql.VARCHAR(charset="ascii", collation="ascii_bin", length=16),
        nullable=False,
        autoincrement=False,
        server_default=text("'public'"),
        comment="public或hidden或deleted",
    )
    edited_at: Mapped[datetime | None] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=True,
        autoincrement=False,
        comment="最后编辑时间",
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


class IssueSubscription(Base):
    """话题独立订阅及主动退订状态。"""

    __tablename__ = "issue_subscriptions"
    __table_args__ = (
        UniqueConstraint("issue_id", "user_id", name="uq_issue_subscriptions_1"),
        ForeignKeyConstraint(
            ["issue_id"],
            ["roadmap_issues.id"],
            name="fk_issue_subscriptions_1",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_issue_subscriptions_2",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        Index("idx_issue_subscriptions_1", "user_id", "is_subscribed", "id"),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=True,
        primary_key=True,
        comment="订阅ID",
    )
    issue_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="主题",
    )
    user_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="订阅人",
    )
    is_subscribed: Mapped[int] = mapped_column(
        mysql.TINYINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        server_default=text("1"),
        comment="0或1，显式退订写0",
    )
    subscription_source: Mapped[str] = mapped_column(
        mysql.VARCHAR(charset="ascii", collation="ascii_bin", length=16),
        nullable=False,
        autoincrement=False,
        comment="author或creator或manual",
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


class IssueEvent(Base):
    """话题状态处理时间线，关闭必须保留原因。"""

    __tablename__ = "issue_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["issue_id"],
            ["roadmap_issues.id"],
            name="fk_issue_events_1",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name="fk_issue_events_2",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        Index("idx_issue_events_1", "issue_id", "created_at", "id"),
        Index("idx_issue_events_fk_2", "actor_id"),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=True,
        primary_key=True,
        comment="事件ID",
    )
    issue_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="主题",
    )
    actor_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="操作者",
    )
    event_type: Mapped[str] = mapped_column(
        mysql.VARCHAR(charset="ascii", collation="ascii_bin", length=24),
        nullable=False,
        autoincrement=False,
        comment="created或edited或resolved或closed或reopened或hidden或restored",
    )
    from_status: Mapped[str | None] = mapped_column(
        mysql.VARCHAR(charset="ascii", collation="ascii_bin", length=16),
        nullable=True,
        autoincrement=False,
        comment="原业务状态，open或resolved或closed",
    )
    to_status: Mapped[str | None] = mapped_column(
        mysql.VARCHAR(charset="ascii", collation="ascii_bin", length=16),
        nullable=True,
        autoincrement=False,
        comment="新业务状态，枚举同上",
    )
    reason: Mapped[str | None] = mapped_column(
        mysql.VARCHAR(length=500),
        nullable=True,
        autoincrement=False,
        comment="处理理由，关闭必填",
    )
    created_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=False,
        autoincrement=False,
        server_default=text("CURRENT_TIMESTAMP(6)"),
        comment="发生时间",
    )
