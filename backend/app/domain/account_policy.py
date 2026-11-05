"""当前账号与持久登录会话的统一授权边界。"""

from app.core.security import AuthClaims, unauthorized, utc_now
from app.database.models.user import User, UserAuthSession


def require_current_user(
    user: User | None, claims: AuthClaims, auth_session: UserAuthSession | None = None
) -> User:
    """写操作锁定后复核账号和会话，JWT解析成功不能替代数据库授权。"""
    if (
        user is None
        or user.id != claims.user_id
        or user.status != "active"
        or auth_session is None
        or auth_session.user_id != user.id
        or auth_session.session_key != claims.session_key
        or auth_session.revoked_at is not None
        or auth_session.expires_at <= utc_now()
    ):
        raise unauthorized()
    return user
