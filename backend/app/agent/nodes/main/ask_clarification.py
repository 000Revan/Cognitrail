"""输出识别阶段给出的澄清问题，结束本轮等待下次用户输入。"""

from langchain_core.messages import AIMessage
from langgraph.config import get_stream_writer

from app.agent.states.chat_state import ChatState


async def ask_clarification(state: ChatState):
    answer = state["clarification_question"]
    get_stream_writer()({"event": "delta", "data": {"text": answer}})
    return {"messages": [AIMessage(content=answer)], "answer": answer}
