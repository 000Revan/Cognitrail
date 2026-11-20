"""调用绑定工具的模型，返回本次回复和循环次数。"""

from langchain_core.messages import SystemMessage
from langgraph.config import get_stream_writer

from app.agent.nodes.stream_model import stream_model
from app.agent.states.chat_state import ChatState


async def call_model(state: ChatState, model_with_tools, system_prompt: str):
    reply = await stream_model(
        model_with_tools,
        [SystemMessage(content=system_prompt), *state["messages"]],
    )
    if reply.tool_calls:
        # 工具调用前的临时文字不与最终回答拼接。
        get_stream_writer()({"event": "reset", "data": {}})
    return {
        "messages": [reply],
        "model_calls": state["model_calls"] + 1,
        "answer": "" if reply.tool_calls else reply.text,
    }
