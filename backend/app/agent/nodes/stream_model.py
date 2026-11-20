"""普通回答与检索流程共用的模型流式输出。"""

from langchain_core.messages import message_chunk_to_message
from langgraph.config import get_stream_writer

from app.core.exceptions import AppError


async def stream_model(model, messages):
    """逐段发送正文，同时合并完整消息供 Graph 判断 tool_calls。"""
    writer = get_stream_writer()
    gathered = None
    async for chunk in model.astream(messages):
        gathered = chunk if gathered is None else gathered + chunk
        if chunk.text:
            writer({"event": "delta", "data": {"text": chunk.text}})
    if gathered is None:
        raise AppError(502, "LLM_EMPTY_RESPONSE", "模型未返回回答，请重试")
    return message_chunk_to_message(gathered)
