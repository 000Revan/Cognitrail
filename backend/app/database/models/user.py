"""公开社区数据模型：users, user_auth_sessions, user_privacy_settings, user_follows。"""

from datetime import datetime

from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint, text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import TABLE_OPTIONS, Base


class User(Base):
    """账号公开资料与当前账号状态。"""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username", name="uq_users_1"),
        Index("idx_users_1", "status", "id"),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=True,
        primary_key=True,
        comment="用户标识",
    )
    username: Mapped[str] = mapped_column(
        mysql.VARCHAR(length=30),
        nullable=False,
        autoincrement=False,
        comment="规范化账号名，创建后不随昵称修改",
    )
    password_hash: Mapped[str] = mapped_column(
        mysql.VARCHAR(length=255),
        nullable=False,
        autoincrement=False,
        comment="不可逆密码散列",
    )
    nickname: Mapped[str] = mapped_column(
        mysql.VARCHAR(length=50),
        nullable=False,
        autoincrement=False,
        comment="公开昵称",
    )
    avatar_url: Mapped[str | None] = mapped_column(
        mysql.VARCHAR(length=2048),
        nullable=True,
        autoincrement=False,
        comment="头像地址，默认头像由前端处理",
    )
    bio: Mapped[str] = mapped_column(
        mysql.VARCHAR(length=500),
        nullable=False,
        autoincrement=False,
        server_default=text("''"),
        comment="公开个人简介",
    )
    role: Mapped[str] = mapped_column(
        mysql.VARCHAR(charset="ascii", collation="ascii_bin", length=16),
        nullable=False,
        autoincrement=False,
        server_default=text("'user'"),
        comment="user或admin",
    )
    status: Mapped[str] = mapped_column(
        mysql.VARCHAR(charset="ascii", collation="ascii_bin", length=16),
        nullable=False,
        autoincrement=False,
        server_default=text("'active'"),
        comment="active或disabled",
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=True,
        autoincrement=False,
        comment="最后登录时间",
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=True,
        autoincrement=False,
        comment="账号停用时间",
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


class UserAuthSession(Base):
    """持久登录会话，独立于学习会话，支持过期及撤销。"""

    __tablename__ = "user_auth_sessions"
    __table_args__ = (
        UniqueConstraint("session_key", name="uq_user_auth_sessions_1"),
        ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_auth_sessions_1",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        Index("idx_user_auth_sessions_1", "user_id", "revoked_at", "expires_at"),
        Index("idx_user_auth_sessions_2", "expires_at"),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=True,
        primary_key=True,
        comment="登录会话ID",
    )
    user_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="登录用户",
    )
    session_key: Mapped[str] = mapped_column(
        mysql.CHAR(charset="ascii", collation="ascii_bin", length=36),
        nullable=False,
        autoincrement=False,
        comment="随机会话标识，可作为JWT中的会话引用",
    )
    issued_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=False,
        autoincrement=False,
        comment="签发时间",
    )
    expires_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=False,
        autoincrement=False,
        comment="会话过期时间",
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=True,
        autoincrement=False,
        comment="撤销时间，退出或改密时设置",
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=True,
        autoincrement=False,
        comment="最后活动时间，可节流更新",
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


class UserPrivacySettings(Base):
    """分类隐私及乐观并发版本，发布默认公开，其他默认私密。"""

    __tablename__ = "user_privacy_settings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_privacy_settings_1",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        TABLE_OPTIONS,
    )
    user_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        primary_key=True,
        comment="一用户一份设置",
    )
    publish_public: Mapped[int] = mapped_column(
        mysql.TINYINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        server_default=text("1"),
        comment="发布活动是否公开，取0或1",
    )
    checkin_public: Mapped[int] = mapped_column(
        mysql.TINYINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        server_default=text("0"),
        comment="打卡活动是否公开",
    )
    favorite_public: Mapped[int] = mapped_column(
        mysql.TINYINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        server_default=text("0"),
        comment="收藏活动及列表是否公开",
    )
    learning_public: Mapped[int] = mapped_column(
        mysql.TINYINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        server_default=text("0"),
        comment="加入学习活动及在学列表是否公开",
    )
    settings_version: Mapped[int] = mapped_column(
        mysql.INTEGER(unsigned=True),
        nullable=False,
        autoincrement=False,
        server_default=text("1"),
        comment="并发和缓存失效版本，正整数",
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

    topic_public: Mapped[int] = mapped_column(
        mysql.TINYINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        server_default=text("0"),
        comment="发布话题动态是否公开",
    )


class UserFollow(Base):
    """用户关注关系，不扩展内容访问或自动订阅。"""

    __tablename__ = "user_follows"
    __table_args__ = (
        UniqueConstraint("follower_id", "followee_id", name="uq_user_follows_1"),
        ForeignKeyConstraint(
            ["follower_id"],
            ["users.id"],
            name="fk_user_follows_1",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["followee_id"],
            ["users.id"],
            name="fk_user_follows_2",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            use_alter=True,
        ),
        Index("idx_user_follows_1", "followee_id", "id"),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=True,
        primary_key=True,
        comment="关系标识",
    )
    follower_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="关注发起人",
    )
    followee_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        nullable=False,
        autoincrement=False,
        comment="被关注人",
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
