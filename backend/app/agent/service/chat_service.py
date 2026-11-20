"""路线检索聊天：checkpoint 保存运行上下文，列表保存最终问答。"""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

from langchain_core.messages import HumanMessage

from app.agent.graph.chat_graph import build_chat_graph
from app.agent.models.chat_model import create_chat_model
from app.agent.prompts.loader import load_prompt
from app.agent.schemas.chat import ChatRequest, ConversationDetail, ConversationSummary
from app.agent.schemas.intent import IntentDecision
from app.agent.tools.route_tools import create_tools
from app.config.settings import settings
from app.core.exceptions import AppError
from app.core.logging import get_logger

logger = get_logger(__name__)

# 单进程临时记录；后端重启或热重载后清空，后续替换为数据库查询与保存。
conversations: list[dict] = []


class ChatService:
    """管理本人会话、运行检索 Graph 并保存最终问答，不依赖 SSE 类型。"""

    @staticmethod
    def get_conversation(conversation_id: str, user_id: int) -> dict:
        """按会话 ID 和当前用户查找，不读取其他用户的记录。"""
        for conversation in conversations:
            if conversation["id"] == conversation_id and conversation["user_id"] == user_id:
                return conversation
        raise AppError(404, "CONVERSATION_NOT_FOUND", "会话不存在，请新建对话")

    @staticmethod
    def list_conversations(user_id: int) -> list[ConversationSummary]:
        """按最近更新时间倒序返回本人的会话摘要，不携带消息。"""
        items = [item for item in conversations if item["user_id"] == user_id]
        items.sort(key=lambda item: item["updated_at"], reverse=True)
        return [ConversationSummary.model_validate(item) for item in items]

    @staticmethod
    def get_messages(conversation_id: str, user_id: int) -> ConversationDetail:
        """返回本人会话及完整的展示历史。"""
        return ConversationDetail.model_validate(
            ChatService.get_conversation(conversation_id, user_id)
        )

    @staticmethod
    async def response(request: ChatRequest, current, sessions) -> AsyncIterator[dict]:
        """返回普通事件字典，由 router 包装成 SSE；失败时不保存半轮问答。"""
        conversation = None
        generating = False
        user_id = current.user.id
        try:
            # 先验证已有会话归属，再创建模型客户端或新会话。
            if request.conversation_id is not None:
                conversation = ChatService.get_conversation(str(request.conversation_id), user_id)
                if conversation["generating"]:
                    raise AppError(409, "CONVERSATION_BUSY", "当前会话正在回答，请稍后再试")

            llm = create_chat_model()
            intent_llm = create_chat_model(thinking=False)
            classifier = intent_llm.with_structured_output(
                IntentDecision, method="function_calling"
            )
            tools = create_tools(current, sessions)
            graph = build_chat_graph(llm, classifier, tools, load_prompt("route_search"))

            if conversation is None:
                now = datetime.now(UTC)
                conversation = {
                    "id": str(uuid4()),
                    "user_id": user_id,
                    "title": request.message[:30],
                    "created_at": now,
                    "updated_at": now,
                    "messages": [],
                    "generating": False,
                }
                conversations.append(conversation)

            conversation["generating"] = True
            generating = True
            yield {"event": "conversation", "data": {"conversationId": conversation["id"]}}

            config = {"configurable": {"thread_id": f"{user_id}:{conversation['id']}"}}
            async with asyncio.timeout(settings.llm_total_timeout_seconds):
                if "checkpoint_config" not in conversation:
                    # 保存空基线；失败重试从上次成功检查点分支，避免残留半轮工具调用。
                    conversation["checkpoint_config"] = await graph.aupdate_state(
                        config,
                        {
                            "messages": [],
                            "model_calls": 0,
                            "tool_failures": {},
                            "answer": "",
                            "active_task": None,
                        },
                        as_node="reply_direct",
                    )
                async for _, event in graph.astream(
                    {
                        "messages": [HumanMessage(content=request.message)],
                        "model_calls": 0,
                        "tool_failures": {},
                        "answer": "",
                        "intent_hint": request.intent_hint,
                        "resolved_intent": None,
                        "clarification_question": "",
                    },
                    config={**conversation["checkpoint_config"], "recursion_limit": 20},
                    stream_mode="custom",
                    subgraphs=True,
                ):
                    yield event
                snapshot = await graph.aget_state(config)
                answer = snapshot.values["answer"]

            if not answer.strip():
                raise AppError(502, "LLM_EMPTY_RESPONSE", "模型未返回回答，请重试")

            # 模型正常结束后一次保存整轮，历史查询不会出现半条回答。
            now = datetime.now(UTC)
            conversation["messages"].extend(
                [
                    {
                        "id": str(uuid4()),
                        "role": role,
                        "content": content,
                        "created_at": now,
                    }
                    for role, content in (("user", request.message), ("assistant", answer))
                ]
            )
            conversation["updated_at"] = now
            conversation["checkpoint_config"] = snapshot.config
            conversation["generating"] = False
            generating = False
            yield {"event": "done", "data": {"conversationId": conversation["id"]}}

        except AppError as exc:
            yield {"event": "error", "data": {"message": exc.message}}
        except TimeoutError:
            yield {"event": "error", "data": {"message": "回答超时，请稍后重试"}}
        except Exception as exc:
            # 不把供应商响应、请求地址或凭证原文发送到前端或日志。
            logger.exception(
                "model_chat_failed",
                error_type=type(exc).__name__,
                conversation_id=conversation["id"] if conversation else None,
            )
            yield {"event": "error", "data": {"message": "模型调用失败，请检查模型配置或稍后重试"}}
        finally:
            if generating:
                conversation["generating"] = False
