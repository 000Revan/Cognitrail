"""循环达到上限后，使用未绑定工具的模型生成最终回答。"""

from langchain_core.messages import AIMessage, SystemMessage

from app.agent.nodes.stream_model import stream_model
from app.agent.states.chat_state import ChatState


async def finish_answer(state: ChatState, llm, system_prompt: str):
    reply = await stream_model(
        llm,
        [
            SystemMessage(
                content=system_prompt
                + "\n本轮工具循环已达上限，停止调用工具。根据已有结果直接回答，"
                "说明未完成的部分，不编造路线或成功结果。"
            ),
            *state["messages"],
        ],
    )
    return {"messages": [AIMessage(content=reply.text)], "answer": reply.text}
