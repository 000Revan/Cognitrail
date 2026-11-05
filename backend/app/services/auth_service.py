"""账号注册、持久登录会话和撤销事务，不依赖旧auth_version。"""

from dataclasses import dataclass
from datetime import timedelta
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.config.enums import UserRole
from app.core.exceptions import AppError
from app.core.security import (
    AuthClaims,
    TokenService,
    dummy_password_hash,
    hash_password,
    utc_now,
    verify_password,
)
from app.database.crud import user as crud
from app.domain.account_policy import require_current_user
from app.schemas.auth import LoginRequest, LoginResponse, RegisterRequest
from app.schemas.user import UserPublic


@dataclass(frozen=True)
class AuthContext:
    """一次授权检查的声明和安全资料快照，写入前仍需重新校验。"""

    claims: AuthClaims
    user: UserPublic


async def authenticated_account(session, claims, *, lock=False):
    """固定先锁用户再锁登录会话；在当前事务重新校验撤销与过期状态。"""
    user = await crud.get_by_id(session, claims.user_id, lock=lock)
    login = await crud.get_auth_session(session, claims.user_id, claims.session_key, lock=lock)
    return require_current_user(user, claims, login)


class AuthService:
    """用户行锁串行化登录、改密、停用，避免旧密码在改密后创建新会话。"""

    def __init__(self, session: AsyncSession, tokens: TokenService) -> None:
        self.session = session
        self.tokens = tokens

    async def register(
        self, data: RegisterRequest, *, role: UserRole = UserRole.USER
    ) -> UserPublic:
        """同事务创建账号与默认隐私；公开路由固定普通用户，不自动登录。"""
        hashed = await hash_password(data.password.get_secret_value())
        try:
            async with self.session.begin():
                user = await crud.add_user(
                    self.session,
                    username=data.username,
                    password_hash=hashed,
                    nickname=data.nickname or data.username,
                    role=role.value,
                )
                await crud.add_privacy(self.session, user.id)
                if role == UserRole.ADMIN:
                    await crud.add_audit(
                        self.session,
                        actor_id=None,
                        action_code="account.bootstrap",
                        target_type="user",
                        target_id=user.id,
                        request_id="bootstrap",
                        result="success",
                        details={"role": "admin"},
                    )
                return UserPublic.model_validate(user)
        except IntegrityError as error:
            if error.orig.args and error.orig.args[0] == 1062:
                raise AppError(409, "USERNAME_EXISTS", "该用户名已被使用") from error
            raise

    async def login(self, data: LoginRequest) -> LoginResponse:
        """验证当前密码与状态，原子保存会话及账号最近登录时间后才返回JWT。"""
        async with self.session.begin():
            user = await crud.get_by_username(self.session, data.username, lock=True)
            hashed = user.password_hash if user else await run_in_threadpool(dummy_password_hash)
            valid = await verify_password(data.password.get_secret_value(), hashed)
            if not valid or user is None or user.status != "active":
                raise AppError(401, "LOGIN_FAILED", "账号或密码错误")
            now = utc_now()
            key = str(uuid4())
            token = self.tokens.create(user.id, key, issued_at=now)
            await crud.add_auth_session(
                self.session,
                user_id=user.id,
                session_key=key,
                issued_at=now,
                expires_at=now + timedelta(seconds=self.tokens.settings.access_token_seconds),
            )
            user.last_login_at = now
            user.updated_at = now
            return LoginResponse(
                access_token=token,
                expires_in=self.tokens.settings.access_token_seconds,
                user=UserPublic.model_validate(user),
            )

    async def authenticate(self, claims: AuthClaims) -> AuthContext:
        """每次读取数据库当前状态、会话归属、撤销与到期，不信任JWT中的角色。"""
        async with self.session.begin():
            user = await authenticated_account(self.session, claims)
            return AuthContext(claims, UserPublic.model_validate(user))

    async def logout(self, claims: AuthClaims) -> None:
        """仅撤销当前登录会话；其他设备保留，改密和停用另行撤销全部会话。"""
        async with self.session.begin():
            await authenticated_account(self.session, claims, lock=True)
            await crud.revoke_sessions(
                self.session, claims.user_id, utc_now(), session_key=claims.session_key
            )
