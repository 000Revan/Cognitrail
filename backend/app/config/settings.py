"""读取环境配置，不在日志中暴露数据库凭证。"""

import re
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """环境变量优先于项目内 .env；数据库密码以 SecretStr 保存。"""

    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Cognitrail"
    app_timezone: str = "Asia/Shanghai"
    db_host: str = "127.0.0.1"
    db_port: int = Field(default=3306, ge=1, le=65535)
    db_name: str = Field(default="cognitrail_community", pattern=r"^[a-zA-Z0-9_]+$")
    db_user: str = "root"
    db_password: SecretStr = SecretStr("")
    db_required_version: str = "8.0.14"
    db_connect_timeout: int = Field(default=3, ge=1, le=30)
    test_db_name: str | None = None
    cors_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]
    log_level: str = "INFO"
    jwt_secret: SecretStr = SecretStr("")
    jwt_algorithm: Literal["HS256"] = "HS256"
    jwt_issuer: str = "cognitrail"
    jwt_audience: str = "cognitrail-web"
    access_token_seconds: int = Field(default=7200, ge=60, le=86400)
    login_rate_limit: int = Field(default=10, ge=1, le=10000)
    login_rate_window_seconds: int = Field(default=60, ge=1, le=3600)
    avatar_storage_dir: Path = BACKEND_ROOT / ".data/avatars"
    avatar_max_bytes: int = Field(default=2 * 1024 * 1024, ge=1, le=20 * 1024 * 1024)
    avatar_max_pixels: int = Field(default=16_000_000, ge=1, le=40_000_000)
    avatar_size: int = Field(default=512, ge=32, le=1024)
    discussion_user_rate_limit: int = Field(default=20, ge=1, le=10000)
    discussion_ip_rate_limit: int = Field(default=60, ge=1, le=10000)
    discussion_rate_window_seconds: int = Field(default=60, ge=1, le=3600)
    outbox_enabled: bool = True
    outbox_poll_seconds: float = Field(default=2, ge=0.1, le=60)
    outbox_lease_seconds: int = Field(default=30, ge=5, le=300)
    outbox_max_attempts: int = Field(default=8, ge=1, le=100)

    @field_validator("app_timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        """尽早拒绝不存在的业务时区。"""
        ZoneInfo(value)
        return value

    def for_community_tests(self) -> "Settings":
        """仅显式独立测试库可用于社区集成测试，不回退到应用或旧数据库。"""
        name = self.test_db_name
        if (
            not name
            or not re.fullmatch(r"cognitrail_community_test(?:_[a-zA-Z0-9]+)*", name)
            or name.casefold() == self.db_name.casefold()
        ):
            raise ValueError(
                "必须显式配置独立 TEST_DB_NAME=cognitrail_community_test 或其下划线后缀名称；"
                "禁止使用旧库或当前应用库"
            )
        return self.model_copy(update={"db_name": name})

    @property
    def database_url(self) -> URL:
        """通过 URL 对象处理密码特殊字符，禁止手工拼接连接串。"""
        return URL.create(
            "mysql+asyncmy",
            username=self.db_user,
            password=self.db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
            query={"charset": "utf8mb4"},
        )
