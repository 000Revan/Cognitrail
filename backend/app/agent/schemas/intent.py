"""主图只接收有限的任务方向，不解析自然语言路由结果。"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

BusinessIntent = Literal["route_search", "route_create"]
Intent = Literal["chat", "route_search", "route_create", "clarify"]


class IntentDecision(BaseModel):
    resolved_intent: Intent = Field(description="本轮应进入的任务方向")
    clarification_question: str = Field(
        description="clarify 时提出一个简短问题，其他方向填空字符串"
    )

    @model_validator(mode="after")
    def require_clarification_question(self):
        if self.resolved_intent == "clarify" and not self.clarification_question.strip():
            raise ValueError("需要澄清时必须提供问题")
        return self
