"""普通交流直接回答，未接入的创作方向明确说明能力范围。"""

from langchain_core.messages import AIMessage, SystemMessage
from langgraph.config import get_stream_writer

from app.agent.nodes.stream_model import stream_model
from app.agent.states.chat_state import ChatState


async def reply_direct(state: ChatState, llm, system_prompt: str):
    if state["resolved_intent"] == "route_create":
        answer = (
            "目前可以帮你检索和比较站内路线，暂不支持生成或保存路线草稿。"
            "你可以告诉我想找的方向，我来查询已有路线。"
        )
        get_stream_writer()({"event": "delta", "data": {"text": answer}})
    else:
        reply = await stream_model(llm, [SystemMessage(content=system_prompt), *state["messages"]])
        answer = reply.text
    return {"messages": [AIMessage(content=answer)], "answer": answer}
