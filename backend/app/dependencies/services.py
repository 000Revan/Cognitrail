"""按请求注入共享会话，服务负责事务。"""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenService
from app.database.session import get_session
from app.services.auth_service import AuthService
from app.services.avatar_service import AvatarStore
from app.services.enrollment_service import EnrollmentService
from app.services.favorite_service import FavoriteService
from app.services.issue_service import IssueService
from app.services.notification_service import NotificationService
from app.services.roadmap_service import RoadmapService
from app.services.user_service import UserService

Session = Annotated[AsyncSession, Depends(get_session)]


def get_auth_service(request: Request, session: Session) -> AuthService:
    return AuthService(session, TokenService(request.app.state.settings))


def get_user_service(request: Request, session: Session) -> UserService:
    return UserService(
        session, request_id=request.state.request_id, avatars=get_avatar_store(request)
    )


def get_avatar_store(request: Request) -> AvatarStore:
    """从当前应用配置创建存储，测试可使用独立临时目录。"""
    return AvatarStore(request.app.state.settings)


def get_roadmap_service(request: Request, session: Session) -> RoadmapService:
    return RoadmapService(session, request.state.request_id)


def get_favorite_service(session: Session) -> FavoriteService:
    return FavoriteService(session)


def get_enrollment_service(request: Request, session: Session) -> EnrollmentService:
    return EnrollmentService(session, request.app.state.settings.app_timezone)


def get_issue_service(session: Session) -> IssueService:
    """话题与身份依赖共享请求会话。"""
    return IssueService(session)


def get_notification_service(session: Session) -> NotificationService:
    """消息中心仅访问当前登录人的消息。"""
    return NotificationService(session)
