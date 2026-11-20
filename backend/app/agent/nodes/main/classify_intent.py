"""结合本轮问题、最近对话和方向提示识别任务。"""

import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.config import get_stream_writer

from app.agent.states.chat_state import ChatState


async def classify_intent(state: ChatState, classifier, system_prompt: str):
    # 最近四轮最终问答加本轮问题；不传工具 JSON 或带工具调用的临时消息。
    recent = []
    for message in state["messages"]:
        if isinstance(message, HumanMessage):
            recent.append(HumanMessage(content=message.text))
        elif isinstance(message, AIMessage) and not message.tool_calls and message.text:
            recent.append(AIMessage(content=message.text))
    context = json.dumps(
        {"intent_hint": state.get("intent_hint"), "active_task": state.get("active_task")},
        ensure_ascii=False,
    )
    decision = await classifier.ainvoke(
        [SystemMessage(content=system_prompt), SystemMessage(content=context), *recent[-9:]]
    )
    intent = decision.resolved_intent
    get_stream_writer()({"event": "intent", "data": {"resolvedIntent": intent}})
    return {
        "resolved_intent": intent,
        "clarification_question": decision.clarification_question,
        "active_task": intent
        if intent in {"route_search", "route_create"}
        else state.get("active_task"),
    }
