"""账号、本人资料与分类隐私契约，拒绝客户端越权字段。"""

from typing import Annotated, Literal

from pydantic import BeforeValidator, ConfigDict, Field, SecretStr, StrictBool, field_validator

from app.config.enums import UserRole
from app.schemas.common import JsonId, Page, Schema, UtcDateTime
from app.schemas.favorite import PublicRoadmap

AccountStatus = Literal["active", "disabled"]
MAX_SETTINGS_VERSION = 2**32 - 1


class PublicIdentity(Schema):
    """社区身份白名单，不含账号状态或私人统计。"""

    id: str
    username: str
    nickname: str
    avatar_url: str | None = None
    bio: str = ""


class FollowState(Schema):
    """关注与粉丝统计不授予任何隐私访问权限。"""

    is_following: bool
    following_count: int
    follower_count: int


class PublicProfile(PublicIdentity, FollowState):
    """公开作品与分类列表均已按当前隐私过滤。"""

    can_follow: bool
    roadmaps: Page[PublicRoadmap]
    can_view_favorites: bool
    can_view_learning: bool
    favorite_count: int | None
    learning_count: int | None


class FollowPerson(PublicIdentity):
    """关系列表按钮以当前查看者为准。"""

    is_following: bool
    can_follow: bool


class ActivitySummary(Schema):
    """按用户日期聚合打卡，绝不返回会话、进度或日历。"""

    id: str
    actor_id: str
    nickname: str
    avatar_url: str | None
    activity_type: Literal["publish", "topic", "checkin"]
    occurred_on: str
    created_at: str
    route_count: int
    roadmap_id: str | None
    title: str | None
    issue_id: str | None = None


def normalize_password(value: object) -> object:
    """保留既有密码规则：先移除全部空白，再验证6–30位。"""
    if isinstance(value, SecretStr):
        value = value.get_secret_value()
    if isinstance(value, str):
        return "".join(value.replace("\ufeff", "").split())
    return value


def normalize_username(value: object) -> object:
    """账号统一为小写ASCII，不依赖数据库排序规则处理大小写。"""
    return value.strip().lower() if isinstance(value, str) else value


Password = Annotated[
    SecretStr, Field(min_length=6, max_length=30), BeforeValidator(normalize_password)
]
Username = Annotated[
    str,
    Field(min_length=3, max_length=30, pattern=r"^[a-z0-9_]+$"),
    BeforeValidator(normalize_username),
]


class UserPublic(Schema):
    """仅输出账号资料和当前状态，不含密码散列或登录会话。"""

    id: JsonId
    username: str
    nickname: str
    avatar_url: str | None = None
    bio: str = ""
    role: UserRole
    status: AccountStatus
    created_at: UtcDateTime


class ProfileUpdate(Schema):
    """PATCH只修改昵称和简介；头像必须通过文件上传接口更换。"""

    model_config = ConfigDict(extra="forbid")
    nickname: str | None = Field(default=None, max_length=50)
    bio: str | None = Field(default=None, max_length=500)

    @field_validator("nickname", "bio", mode="before")
    @classmethod
    def normalize_text(cls, value: object, info):
        """拒绝显式NULL；昵称去空白后不能为空，简介可清空。"""
        if not isinstance(value, str):
            raise ValueError("必须填写文本")
        value = value.strip()
        if info.field_name == "nickname" and not value:
            raise ValueError("昵称不能为空")
        return value


class AccountStatusUpdate(Schema):
    """管理员修改状态时提交原状态，避免并发覆盖。"""

    model_config = ConfigDict(extra="forbid")
    status: AccountStatus
    expected_status: AccountStatus


class AccountCreate(Schema):
    """管理员创建账号可选角色；公开注册不得传角色。"""

    model_config = ConfigDict(extra="forbid")
    username: Username
    nickname: str | None = Field(default=None, max_length=50)
    password: Password
    role: UserRole = UserRole.USER

    @field_validator("nickname")
    @classmethod
    def normalize_nickname(cls, value: str | None) -> str | None:
        """未提供昵称时由服务层使用规范化用户名。"""
        return value.strip() or None if value is not None else None


class AccountProfileUpdate(Schema):
    """管理员昵称编辑必须提交原昵称，不允许修改其他资料字段。"""

    model_config = ConfigDict(extra="forbid")
    nickname: str = Field(min_length=1, max_length=50)
    expected_nickname: str = Field(min_length=1, max_length=50)

    @field_validator("nickname")
    @classmethod
    def normalize_nickname(cls, value: str) -> str:
        """不允许以空白昵称绕过非空约束。"""
        if not value.strip():
            raise ValueError("昵称不能为空")
        return value.strip()


class AccountPasswordReset(Schema):
    """管理员重置普通用户密码，不返回密码或签发会话。"""

    model_config = ConfigDict(extra="forbid")
    new_password: Password


class PasswordUpdate(Schema):
    """本人改密必须验证原密码，成功后全部会话失效。"""

    model_config = ConfigDict(extra="forbid")
    old_password: Password
    new_password: Password


class PrivacySettings(Schema):
    """五项公开范围独立；不开放详细进度或个人日历。"""

    publish_public: bool
    topic_public: bool
    checkin_public: bool
    favorite_public: bool
    learning_public: bool
    settings_version: int


class PrivacyUpdate(Schema):
    """五项隐私及严格版本；旧客户端省略话题字段时保留该选择。"""

    model_config = ConfigDict(extra="forbid")
    publish_public: StrictBool
    topic_public: StrictBool | None = None
    checkin_public: StrictBool
    favorite_public: StrictBool
    learning_public: StrictBool
    settings_version: int = Field(strict=True, ge=1, le=MAX_SETTINGS_VERSION)

    @field_validator("topic_public", mode="before")
    @classmethod
    def validate_topic_visibility(cls, value):
        """旧客户端省略时保留原值，显式NULL和非布尔值拒绝。"""
        if not isinstance(value, bool):
            raise ValueError("必须填写布尔值")
        return value
