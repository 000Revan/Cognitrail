"""与 V2.5 数据库 CHECK 保持一致的业务枚举。"""

from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    USER = "user"


class RoadmapType(StrEnum):
    OFFICIAL = "official"
    USER = "user"


class Difficulty(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class ResourceType(StrEnum):
    BOOK = "book"
    ARTICLE = "article"
    VIDEO = "video"
    DOCUMENT = "document"
    COURSE = "course"
    OTHER = "other"
