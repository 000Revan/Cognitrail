"""检索 ReAct 的消息与本轮计数；由 checkpointer 按会话保存。"""

from langgraph.graph import MessagesState

from app.agent.schemas.intent import BusinessIntent, Intent


class ChatState(MessagesState):
    intent_hint: BusinessIntent | None
    resolved_intent: Intent | None
    active_task: BusinessIntent | None
    clarification_question: str
    model_calls: int
    tool_failures: dict[str, int]
    answer: str
