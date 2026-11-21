"""助手会话和消息读写；事务由 ChatService 管理。"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import func, select

from app.database.models.agent import AgentConversation, AgentMessage


async def get_conversation(session, conversation_id: str, user_id: int):
    """按会话及用户共同过滤，不暴露其他用户会话是否存在。"""
    return await session.scalar(
        select(AgentConversation).where(
            AgentConversation.id == conversation_id,
            AgentConversation.user_id == user_id,
        )
    )


async def create_conversation(session, user_id: int, title: str, now: datetime):
    """创建空会话；成功问答在运行结束后保存。"""
    row = AgentConversation(
        id=str(uuid4()),
        user_id=user_id,
        title=title,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    await session.flush()
    return row


async def list_conversations(session, user_id: int):
    """仅查询本人会话，最近更新的在前。"""
    return list(
        await session.scalars(
            select(AgentConversation)
            .where(AgentConversation.user_id == user_id)
            .order_by(AgentConversation.updated_at.desc(), AgentConversation.id.desc())
        )
    )


async def list_messages(session, conversation_id: str):
    """在 service 完成归属校验后读取最终消息。"""
    return list(
        await session.scalars(
            select(AgentMessage)
            .where(AgentMessage.conversation_id == conversation_id)
            .order_by(AgentMessage.position)
        )
    )


async def save_completed_turn(
    session, conversation, question: str, answer: str, checkpoint_id: str, now: datetime
):
    """在同一业务事务中追加两条消息并推进成功检查点。"""
    position = await session.scalar(
        select(func.coalesce(func.max(AgentMessage.position), 0)).where(
            AgentMessage.conversation_id == conversation.id
        )
    )
    session.add_all(
        [
            AgentMessage(
                id=str(uuid4()),
                conversation_id=conversation.id,
                position=position + offset,
                role=role,
                content=content,
                created_at=now,
            )
            for offset, (role, content) in enumerate((("user", question), ("assistant", answer)), 1)
        ]
    )
    conversation.last_checkpoint_id = checkpoint_id
    conversation.updated_at = now
    await session.flush()
