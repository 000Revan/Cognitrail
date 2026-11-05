"""固定算法 JWT 与在线程池执行的 Argon2，不记录密码或凭证。"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from uuid import UUID

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from starlette.concurrency import run_in_threadpool

from app.config.settings import Settings
from app.core.exceptions import AppError

password_hasher = PasswordHash.recommended()


@dataclass(frozen=True)
class AuthClaims:
    user_id: int
    session_key: str


def utc_now() -> datetime:
    """MySQL DATETIME统一保存无时区UTC，避免与带时区值比较。"""
    return datetime.now(UTC).replace(tzinfo=None)


def unauthorized() -> AppError:
    """所有失效/伪造凭证使用统一错误，不暴露校验细节。"""
    return AppError(401, "INVALID_CREDENTIALS", "登录已失效，请重新登录")


async def hash_password(password: str) -> str:
    """CPU 密集哈希离开事件循环执行。"""
    return await run_in_threadpool(password_hasher.hash, password)


async def verify_password(password: str, hashed: str) -> bool:
    """损坏的哈希按验证失败处理，避免暴露内部格式。"""
    try:
        return await run_in_threadpool(password_hasher.verify, password, hashed)
    except (ValueError, UnknownHashError):
        return False


@lru_cache(maxsize=1)
def dummy_password_hash() -> str:
    """不存在账号也执行一次 Argon2 验证，减少枚举的时延差。"""
    return password_hasher.hash("dummy-password-never-used-to-authenticate")


class TokenService:
    """只处理签名与声明，不信任 JWT 中的角色。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _key(self) -> str:
        key = self.settings.jwt_secret.get_secret_value()
        if len(key.encode("utf-8")) < 32:
            raise AppError(503, "AUTH_NOT_CONFIGURED", "账号服务尚未配置")
        return key

    def create(self, user_id: int, session_key: str, *, issued_at: datetime | None = None) -> str:
        """JWT只引用随机持久会话；不能以旧authVersion替代数据库撤销检查。"""
        now = (issued_at or utc_now()).replace(tzinfo=UTC)
        return jwt.encode(
            {
                "sub": str(user_id),
                "sid": session_key,
                "iat": now,
                "exp": now + timedelta(seconds=self.settings.access_token_seconds),
                "iss": self.settings.jwt_issuer,
                "aud": self.settings.jwt_audience,
            },
            self._key(),
            algorithm=self.settings.jwt_algorithm,
        )

    def decode(self, token: str) -> AuthClaims:
        """校验签名及必填声明、无符号ID和规范UUID；旧版凭证拒绝。"""
        try:
            claims = jwt.decode(
                token,
                self._key(),
                algorithms=[self.settings.jwt_algorithm],
                issuer=self.settings.jwt_issuer,
                audience=self.settings.jwt_audience,
                options={"require": ["sub", "exp", "iat", "iss", "aud", "sid"]},
            )
            user_id, session_key = claims["sub"], claims["sid"]
            if (
                not isinstance(user_id, str)
                or len(user_id) > 20
                or not user_id.isascii()
                or not user_id.isdecimal()
                or not 0 < int(user_id) <= 2**64 - 1
                or not isinstance(session_key, str)
                or len(session_key) != 36
                or str(UUID(session_key)) != session_key
                or type(claims["iat"]) is not int
                or type(claims["exp"]) is not int
                or claims["exp"] <= claims["iat"]
            ):
                raise unauthorized()
            return AuthClaims(int(user_id), session_key)
        except (jwt.InvalidTokenError, ValueError, TypeError) as error:
            raise unauthorized() from error
