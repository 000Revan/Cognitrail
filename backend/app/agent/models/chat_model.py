from langchain_openai import ChatOpenAI  # 使用 OpenAI 或兼容接口调用聊天模型。

from app.config.settings import settings
from app.core.exceptions import AppError  # 复用项目现有错误响应机制。


def create_chat_model(*, thinking: bool = True) -> ChatOpenAI:
    """读取共享配置，按用途切换 DeepSeek 思考模式。"""

    if not settings.llm_api_key.get_secret_value() or not settings.llm_model:
        raise AppError(
            503,  # 模型未配置时，接口暂不可用。
            "LLM_NOT_CONFIGURED",  # 提供稳定的错误码。
            "请先配置模型名称和 API Key",  # 前端可直接展示的提示。
        )

    return ChatOpenAI(
        model=settings.llm_model,  # 使用配置指定的模型。
        api_key=settings.llm_api_key.get_secret_value(),  # 取出真实密钥交给客户端。
        base_url=settings.llm_base_url or None,  # 空地址时使用 SDK 默认地址。
        timeout=settings.llm_timeout_seconds,  # 设置网络请求超时。
        max_retries=0,  # 本次失败直接反馈，不在基础链路内自动重试。
        max_tokens=2048,  # 限制单次回答长度。
        extra_body={"thinking": {"type": "enabled" if thinking else "disabled"}},
    )
