"""集中注册31张社区业务表；导入只建立映射，不连接或创建数据库。"""

from app.database.models.activity import ActivityEvent
from app.database.models.enrollment import LearningSession, LearningSessionEvent, UserRoadmap
from app.database.models.favorite import RoadmapFavorite, RoadmapSubscription
from app.database.models.issue import IssueComment, IssueEvent, IssueSubscription, RoadmapIssue
from app.database.models.moderation import AuditLog, ContentReport, ModerationAction
from app.database.models.node import LearningNode
from app.database.models.node_progress import UserNodeProgress
from app.database.models.notification import Notification, NotificationOutbox
from app.database.models.release import (
    ReleaseNode,
    ReleaseResource,
    ReleaseStage,
    ReleaseStageEdge,
    RoadmapRelease,
)
from app.database.models.resource import NodeResource
from app.database.models.roadmap import SkillRoadmap
from app.database.models.stage import RoadmapStage, RoadmapStageEdge
from app.database.models.study_record import RoadmapCheckin
from app.database.models.study_record import StudyRecord as StudyRecord
from app.database.models.user import User, UserAuthSession, UserFollow, UserPrivacySettings

# StudyRecord仅保留旧服务的导入失败边界，不属于业务ORM导出。
__all__ = [
    "ActivityEvent",
    "AuditLog",
    "ContentReport",
    "IssueComment",
    "IssueEvent",
    "IssueSubscription",
    "LearningNode",
    "LearningSession",
    "LearningSessionEvent",
    "ModerationAction",
    "NodeResource",
    "Notification",
    "NotificationOutbox",
    "ReleaseNode",
    "ReleaseResource",
    "ReleaseStage",
    "ReleaseStageEdge",
    "RoadmapCheckin",
    "RoadmapFavorite",
    "RoadmapIssue",
    "RoadmapRelease",
    "RoadmapStage",
    "RoadmapStageEdge",
    "RoadmapSubscription",
    "SkillRoadmap",
    "User",
    "UserAuthSession",
    "UserFollow",
    "UserNodeProgress",
    "UserPrivacySettings",
    "UserRoadmap",
]
