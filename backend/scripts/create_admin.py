"""交互式创建管理员，不接受命令行明文密码。"""

import argparse
import asyncio
from getpass import getpass

from pydantic import ValidationError

from app.config.enums import UserRole
from app.config.settings import Settings
from app.core.exceptions import AppError
from app.core.security import TokenService
from app.database import validation
from app.database.session import Database
from app.schemas.auth import RegisterRequest
from app.schemas.user import normalize_password
from app.services.auth_service import AuthService


def require_admin_creation_ready() -> None:
    """管理员创建模块关闭时，命令行也不能绕过开放边界。"""
    if ("POST", "/api/v1/admin/users") not in validation.COMMUNITY_ENABLED_ENDPOINTS:
        raise AppError(503, "COMMUNITY_FEATURE_NOT_READY", "管理员初始化暂未开放，需先完成R02适配")


async def create(data: RegisterRequest) -> None:
    """交互式创建管理员并原子初始化隐私，不自动签发登录会话。"""
    require_admin_creation_ready()
    settings = Settings()
    database = Database(settings)
    try:
        async with database.sessions() as session:
            await AuthService(session, TokenService(settings)).register(data, role=UserRole.ADMIN)
        print("管理员已创建")
    finally:
        await database.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="创建知途工坊管理员")
    parser.add_argument("--username", required=True)
    parser.add_argument("--nickname", default=None)
    arguments = parser.parse_args()
    try:
        require_admin_creation_ready()
    except AppError as error:
        raise SystemExit(error.message) from None
    password = normalize_password(getpass("管理员密码（6–30 位，自动去除空白）："))
    if password != normalize_password(getpass("再次输入密码：")):
        raise SystemExit("两次密码不一致，未创建")
    try:
        data = RegisterRequest(
            username=arguments.username, password=password, nickname=arguments.nickname
        )
        asyncio.run(create(data))
    except ValidationError:
        raise SystemExit("账号格式、密码长度或昵称不符合要求，未创建") from None
    except AppError as error:
        raise SystemExit(error.message) from None
    except Exception as error:
        raise SystemExit(f"创建失败（{type(error).__name__}），请检查数据库配置") from None


if __name__ == "__main__":
    main()
