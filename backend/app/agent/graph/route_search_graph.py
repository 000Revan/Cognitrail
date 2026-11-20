"""站内路线检索子图：保留原有 ReAct 循环与失败预算。"""

from functools import partial

from langgraph.graph import END, START, StateGraph

from app.agent.nodes.route_search.call_model import call_model
from app.agent.nodes.route_search.execute_tools import execute_tools
from app.agent.nodes.route_search.finish_answer import finish_answer
from app.agent.states.chat_state import ChatState

MAX_MODEL_CALLS = 5


def after_model(state: ChatState):
    return "tools" if state["messages"][-1].tool_calls else END


def after_tools(state: ChatState):
    return "finish_answer" if state["model_calls"] >= MAX_MODEL_CALLS else "model"


def build_route_search_graph(llm, tools, system_prompt: str):
    """创建本次请求的 Graph，工具实例已绑定当前用户。"""
    model_with_tools = llm.bind_tools(tools)
    tools_by_name = {item.name: item for item in tools}

    builder = StateGraph(ChatState)
    # 绑定本次请求的依赖，Graph 运行时只需传入 state。
    builder.add_node(
        "model",
        partial(call_model, model_with_tools=model_with_tools, system_prompt=system_prompt),
    )
    builder.add_node("tools", partial(execute_tools, tools_by_name=tools_by_name))
    builder.add_node("finish_answer", partial(finish_answer, llm=llm, system_prompt=system_prompt))
    builder.add_edge(START, "model")
    builder.add_conditional_edges("model", after_model)
    builder.add_conditional_edges("tools", after_tools)
    builder.add_edge("finish_answer", END)
    return builder.compile()
