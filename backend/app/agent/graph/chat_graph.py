"""每轮识别一次意图，再进入直接回答、澄清或检索子图。"""

from functools import partial

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from app.agent.graph.route_search_graph import build_route_search_graph
from app.agent.nodes.main.ask_clarification import ask_clarification
from app.agent.nodes.main.classify_intent import classify_intent
from app.agent.nodes.main.reply_direct import reply_direct
from app.agent.prompts.loader import load_prompt
from app.agent.states.chat_state import ChatState

# 主图按用户和会话保存上下文；子图继承，模型与工具仍按请求绑定。
checkpointer = InMemorySaver()


def route_by_intent(state: ChatState):
    return {
        "chat": "reply_direct",
        "route_search": "route_search",
        "route_create": "reply_direct",
        "clarify": "ask_clarification",
    }[state["resolved_intent"]]


def build_chat_graph(llm, classifier, tools, system_prompt: str):
    """构建主图；创作流程尚未接入，先明确反馈当前能力。"""
    search_graph = build_route_search_graph(llm, tools, system_prompt)
    builder = StateGraph(ChatState)
    builder.add_node(
        "classify_intent",
        partial(classify_intent, classifier=classifier, system_prompt=load_prompt("intent_router")),
    )
    builder.add_node(
        "reply_direct", partial(reply_direct, llm=llm, system_prompt=load_prompt("chat"))
    )
    builder.add_node("ask_clarification", ask_clarification)
    builder.add_node("route_search", search_graph)
    builder.add_edge(START, "classify_intent")
    builder.add_conditional_edges("classify_intent", route_by_intent)
    builder.add_edge("reply_direct", END)
    builder.add_edge("ask_clarification", END)
    builder.add_edge("route_search", END)
    return builder.compile(checkpointer=checkpointer)
