"""MySQL 保存展示历史，checkpointer 保存 Graph 状态和工具消息。"""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from langchain_core.messages import HumanMessage
from sqlalchemy.exc import SQLAlchemyError

from app.agent.graph.chat_graph import build_chat_graph
from app.agent.models.chat_model import create_chat_model
from app.agent.prompts.loader import load_prompt
from app.agent.schemas.chat import ChatRequest, ConversationDetail, ConversationSummary
from app.agent.schemas.intent import IntentDecision
from app.agent.tools.route_tools import create_tools
from app.config.settings import settings
from app.core.exceptions import AppError
from app.core.logging import get_logger
from app.database.crud import agent as agent_crud

logger = get_logger(__name__)

# 仅保存正在执行的 ID，不保存历史；当前仍使用单 worker。
generating_conversations: set[tuple[int, str]] = set()


class ChatService:
    """协调短数据库事务、Graph 运行和成功轮次提交。"""

    @staticmethod
    async def get_conversation(session, conversation_id: str, user_id: int):
        """读取本人会话，不存在或越权统一返回 404。"""
        conversation = await agent_crud.get_conversation(session, conversation_id, user_id)
        if conversation is None:
            raise AppError(404, "CONVERSATION_NOT_FOUND", "会话不存在，请新建对话")
        return conversation

    @staticmethod
    async def list_conversations(user_id: int, sessions) -> list[ConversationSummary]:
        """历史列表只查询 MySQL，不运行 Graph 或模型。"""
        async with sessions() as session:
            rows = await agent_crud.list_conversations(session, user_id)
            return [ConversationSummary.model_validate(row) for row in rows]

    @staticmethod
    async def get_messages(conversation_id: str, user_id: int, sessions) -> ConversationDetail:
        """先校验归属，再按消息顺序返回 MySQL 中成功保存的最终问答。"""
        async with sessions() as session:
            conversation = await ChatService.get_conversation(session, conversation_id, user_id)
            messages = await agent_crud.list_messages(session, conversation_id)
            return ConversationDetail(
                **ConversationSummary.model_validate(conversation).model_dump(by_alias=False),
                messages=messages,
            )

    @staticmethod
    async def response(
        request: ChatRequest, current, sessions, checkpointer
    ) -> AsyncIterator[dict]:
        """失败轮次不推进成功指针；提交最终问答后才发送 done。"""
        conversation = None
        conversation_key = None
        user_id = current.user.id
        try:
            # 已有会话先校验归属，关闭读取 session 后才开始生成。
            if request.conversation_id is not None:
                key = (user_id, str(request.conversation_id))
                if key in generating_conversations:
                    raise AppError(409, "CONVERSATION_BUSY", "当前会话正在回答，请稍后再试")
                # 在第一次数据库读取前认领，避免读到并发轮次提交前的旧成功指针。
                generating_conversations.add(key)
                conversation_key = key
                async with sessions() as session:
                    conversation = await ChatService.get_conversation(
                        session, str(request.conversation_id), user_id
                    )

            llm = create_chat_model()
            intent_llm = create_chat_model(thinking=False)
            classifier = intent_llm.with_structured_output(
                IntentDecision, method="function_calling"
            )
            tools = create_tools(current, sessions)
            graph = build_chat_graph(
                llm, classifier, tools, load_prompt("route_search"), checkpointer
            )

            if conversation is None:
                async with sessions() as session, session.begin():
                    conversation = await agent_crud.create_conversation(
                        session,
                        user_id,
                        request.message[:30],
                        datetime.now(UTC).replace(tzinfo=None),
                    )

            if conversation_key is None:
                conversation_key = (user_id, conversation.id)
                generating_conversations.add(conversation_key)
            yield {"event": "conversation", "data": {"conversationId": conversation.id}}
            config = {
                "configurable": {"thread_id": f"{user_id}:{conversation.id}", "checkpoint_ns": ""}
            }

            async with asyncio.timeout(settings.llm_total_timeout_seconds):
                if conversation.last_checkpoint_id is None:
                    # 基线指针先提交；首轮失败/重启后也不会误用失败检查点。
                    baseline = await graph.aupdate_state(
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
                    async with sessions() as session, session.begin():
                        row = await ChatService.get_conversation(session, conversation.id, user_id)
                        row.last_checkpoint_id = baseline["configurable"]["checkpoint_id"]
                    conversation.last_checkpoint_id = row.last_checkpoint_id

                run_config = {
                    "configurable": {
                        **config["configurable"],
                        "checkpoint_id": conversation.last_checkpoint_id,
                    },
                    "recursion_limit": 20,
                }
                saved = await graph.aget_state(run_config)
                if saved.created_at is None:
                    raise AppError(
                        409,
                        "CONVERSATION_STATE_MISSING",
                        "会话运行记录缺失，历史仍可查看，请新建对话",
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
                    config=run_config,
                    stream_mode="custom",
                    subgraphs=True,
                    durability="sync",
                ):
                    yield event
                snapshot = await graph.aget_state(config)
                answer = snapshot.values["answer"]

            if not answer.strip():
                raise AppError(502, "LLM_EMPTY_RESPONSE", "模型未返回回答，请重试")

            # SQLite 检查点已落盘；业务事务只提交两条消息和对应成功指针。
            async with sessions() as session, session.begin():
                row = await ChatService.get_conversation(session, conversation.id, user_id)
                await agent_crud.save_completed_turn(
                    session,
                    row,
                    request.message,
                    answer,
                    snapshot.config["configurable"]["checkpoint_id"],
                    datetime.now(UTC).replace(tzinfo=None),
                )
            yield {"event": "done", "data": {"conversationId": conversation.id}}

        except AppError as exc:
            yield {"event": "error", "data": {"message": exc.message}}
        except TimeoutError:
            yield {"event": "error", "data": {"message": "回答超时，请稍后重试"}}
        except SQLAlchemyError:
            logger.exception(
                "agent_history_failed", conversation_id=conversation.id if conversation else None
            )
            yield {
                "event": "error",
                "data": {"message": "会话数据读写失败，请检查数据库连接与迁移后重试"},
            }
        except Exception as exc:
            logger.exception(
                "model_chat_failed",
                error_type=type(exc).__name__,
                conversation_id=conversation.id if conversation else None,
            )
            yield {"event": "error", "data": {"message": "模型调用失败，请检查模型配置或稍后重试"}}
        finally:
            if conversation_key is not None:
                generating_conversations.discard(conversation_key)
