"""基础对话请求与历史展示契约。"""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints

from app.agent.schemas.intent import BusinessIntent
from app.schemas.common import Schema, UtcDateTime

QuestionText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)
]


class ChatRequest(Schema):
    message: QuestionText
    conversation_id: UUID | None = None
    intent_hint: BusinessIntent | None = None


class ChatMessage(Schema):
    id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: UtcDateTime


class ConversationSummary(Schema):
    id: str
    title: str
    created_at: UtcDateTime
    updated_at: UtcDateTime


class ConversationDetail(ConversationSummary):
    messages: list[ChatMessage] = Field(default_factory=list)
