"""R04公开卡片与私人收藏契约，受限收藏不携带路线内容。"""

from app.schemas.common import Schema


class PublicAuthor(Schema):
    """仅包含作者公开摘要，不包含账号状态或私人设置。"""

    id: str
    username: str
    nickname: str
    avatar_url: str | None
    bio: str | None


class PublicRoadmap(Schema):
    """仅含当前发布摘要及独立聚合计数，不含正文或资源。"""

    id: str
    title: str
    description: str | None
    difficulty: str
    cover_url: str | None
    roadmap_type: str
    release_id: str
    version_no: int
    published_at: str
    stage_count: int
    node_count: int
    learner_count: int
    favorite_count: int
    is_favorited: bool
    is_owner: bool
    author: PublicAuthor


class PublicRoadmapPage(Schema):
    """社区分页结果。"""

    items: list[PublicRoadmap]
    total: int
    page: int
    page_size: int


class FavoriteResult(Schema):
    """幂等收藏写操作的最终状态。"""

    roadmap_id: str
    is_favorited: bool
    favorite_count: int


class FavoriteItem(Schema):
    """不可访问时仅保留最小摘要和取消入口，不返回工作稿。"""

    roadmap_id: str
    title: str
    status: str
    accessible: bool
    favorited_at: str
    roadmap: PublicRoadmap | None


class FavoritePage(Schema):
    """当前用户的收藏分页。"""

    items: list[FavoriteItem]
    total: int
    page: int
    page_size: int
