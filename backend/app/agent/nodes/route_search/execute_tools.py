"""执行模型请求的工具，记录失败预算并返回 ToolMessage。"""

import asyncio
import json

from langchain_core.messages import ToolMessage
from langchain_core.tools import ToolException
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.agent.states.chat_state import ChatState
from app.core.exceptions import AppError

MAX_TOOL_FAILURES = 3


async def execute_tools(state: ChatState, tools_by_name):
    failures = dict(state["tool_failures"])
    results = []
    for call in state["messages"][-1].tool_calls:
        name = call["name"]
        selected_tool = tools_by_name.get(name)
        status = "error"
        if selected_tool is None:
            content = "工具不存在，请使用已提供的工具。"
        elif failures.get(name, 0) >= MAX_TOOL_FAILURES:
            content = "该工具本轮累计失败已达到 3 次，请停止调用并说明限制。"
        else:
            while True:
                try:
                    result = await selected_tool.ainvoke(call["args"])
                    content = json.dumps(result, ensure_ascii=False)
                    status = "success"
                    break
                except ValidationError as exc:
                    failures[name] = failures.get(name, 0) + 1
                    content = json.dumps(
                        exc.errors(include_url=False, include_input=False, include_context=False),
                        ensure_ascii=False,
                    )
                    content = "参数校验失败，请修改参数：" + content
                    break
                except (TimeoutError, ConnectionError, OperationalError) as exc:
                    if isinstance(exc, OperationalError) and not (
                        exc.connection_invalidated
                        or (
                            exc.orig.args
                            and exc.orig.args[0] in {2002, 2003, 2006, 2013, 1205, 1213}
                        )
                    ):
                        failures[name] = MAX_TOOL_FAILURES
                        content = "数据库查询不可用，请检查服务配置；不能视为没有匹配路线。"
                        break
                    failures[name] = failures.get(name, 0) + 1
                    if failures[name] >= MAX_TOOL_FAILURES:
                        content = "查询暂时失败，已达到本轮失败上限；不能视为没有匹配路线。"
                        break
                    await asyncio.sleep(failures[name])
                except (AppError, ToolException) as exc:
                    failures[name] = failures.get(name, 0) + 1
                    if isinstance(exc, AppError) and exc.status_code in {401, 403}:
                        failures[name] = MAX_TOOL_FAILURES
                    content = exc.message if isinstance(exc, AppError) else str(exc)
                    break
                except SQLAlchemyError:
                    failures[name] = MAX_TOOL_FAILURES
                    content = "路线查询失败，请稍后重试；不能视为没有匹配路线。"
                    break
            if status == "error":
                remaining = MAX_TOOL_FAILURES - failures.get(name, 0)
                content += f" 本轮该工具剩余失败额度：{remaining}。"
        results.append(
            ToolMessage(
                content=content,
                name=name,
                tool_call_id=call["id"],
                status=status,
            )
        )
    return {"messages": results, "tool_failures": failures}
