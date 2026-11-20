"""基础对话、本人会话列表及消息查询。"""

from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.agent.schemas.chat import ChatRequest, ConversationDetail, ConversationSummary
from app.agent.service.chat_service import ChatService
from app.dependencies.auth import CurrentUser
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/agent", tags=["智能助手"])


@router.post("/chat", response_class=EventSourceResponse)
async def chat(data: ChatRequest, current: CurrentUser, request: Request):
    """接收问题及可选会话 ID，将服务事件转换成 SSE。"""
    async for event in ChatService.response(data, current, request.app.state.database.sessions):
        yield ServerSentEvent(data=event["data"], event=event["event"])


@router.get("/conversations", response_model=ApiResponse[list[ConversationSummary]])
async def list_conversations(current: CurrentUser):
    """读取左侧会话列表。"""
    return ApiResponse(data=ChatService.list_conversations(current.user.id))


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=ApiResponse[ConversationDetail],
)
async def get_conversation_messages(conversation_id: UUID, current: CurrentUser):
    """读取选中会话的历史消息。"""
    return ApiResponse(data=ChatService.get_messages(str(conversation_id), current.user.id))
