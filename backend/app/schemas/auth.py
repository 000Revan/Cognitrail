"""注册不自动登录；登录仅返回访问凭证，不提供刷新令牌。"""

from typing import Literal

from pydantic import ConfigDict, Field, field_validator

from app.schemas.common import Schema
from app.schemas.user import Password, Username, UserPublic


class LoginRequest(Schema):
    """登录使用规范化账号名，拒绝额外权限字段。"""

    model_config = ConfigDict(extra="forbid")
    username: Username
    password: Password


class RegisterRequest(LoginRequest):
    """公开注册固定普通用户，昵称省略时使用账号名。"""

    nickname: str | None = Field(default=None, max_length=50)

    @field_validator("nickname")
    @classmethod
    def normalize_nickname(cls, value: str | None) -> str | None:
        """可省略昵称，服务层原子初始化非空显示名及默认隐私。"""
        return value.strip() or None if value is not None else None


class LoginResponse(Schema):
    """仅返回当前访问令牌、有效秒数及安全账号资料。"""

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserPublic
