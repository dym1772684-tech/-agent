from langchain.agents.middleware import wrap_tool_call, SummarizationMiddleware,HumanInTheLoopMiddleware
from langchain.messages import RemoveMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langgraph.checkpoint.memory import InMemorySaver
from langchain.agents import create_agent, AgentState
from langchain.agents.middleware import before_model,after_model,hook_config
from langgraph.runtime import Runtime
from langchain.messages import HumanMessage,AIMessage
from langchain_core.runnables import RunnableConfig
from typing import Any
from allagent.agent.state import state_schema
@before_model
def trim_messages(state: state_schema, runtime: Runtime) -> dict[str, Any] | None:
    """Keep only the last few messages to fit context window."""
    messages = state["messages"]

    if len(messages) <= 3:
        return None  # No changes needed

    first_msg = messages[0] 
    recent_messages = messages[-3:] if len(messages) % 2 == 0 else messages[-4:]
    new_messages = [first_msg] + recent_messages

    return {
        "messages": [
            RemoveMessage(id=REMOVE_ALL_MESSAGES),
            *new_messages
        ]
    }
@after_model
def delete_messages(state:state_schema,runtime:Runtime):
    messages=state["messages"]
@wrap_tool_call
def check_rag_privacy(state:state_schema):
    for i in state["messages"]:
        if isinstance(i,HumanMessage):
            pass
@after_model
def add_ai_think(state:state_schema,response):###GraphOutput
    aithink=[b for b in response.content_blocks if b["type"]=="reasoning"]
    complete_aithink="".join(step["reasoning"] for step in aithink)
    state.ai_content=state.ai_content.append(complete_aithink)#########用来充当中间件 提取每一次的aithink ，进入任何节点之后的
# before_agent	代理人开始前（每次调用一次）
# before_model	每次模型调用前
# after_model	每次模型响应后
# after_agent	代理完成后（每次调用一次）
# 每个调用都环绕着 Wrap 风格的钩子，让你控制执行：
# 胡克	当它运行时
# wrap_model_call	围绕每个模型调用
# wrap_tool_call	围绕每个工具调用


