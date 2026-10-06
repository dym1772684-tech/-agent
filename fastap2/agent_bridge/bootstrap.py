"""集成引导层（胶水层）核心。

职责：
1. 定位并加载两个项目的 .env 配置；
2. 在 sys.path / sys.modules 中把 allagent2 目录以包名 `allagent` 注册，
   使其内部大量的 `from allagent.xxx import ...` 全部生效（无需改动原文件）；
3. 在导入 graph 之前，把后端只读能力（查老人档案 / 查健康记录）动态注入
   allagent 的工具列表（graph 顶层 create_tool_model 会 bind_tools）；
4. 编译 LangGraph，并提供与原 graph.py 交互入口一致的 run_agent 调用。
"""
from __future__ import annotations

import importlib
import logging
import os
import sys
import threading  # 【健壮性】用于首次引导的线程锁
import types
from pathlib import Path
from typing import Any, Dict

# 【安全】链路过程日志：整个 Agent 数据链路（节点/消息/工具调用/元数据）只允许出现在日志里，
# 绝不回传前端；前端只能看到智能体的最终回答。
# 【健壮性】agent_bridge 自带控制台 handler（与 allagent2 的 logging_helper 对齐），
# 不依赖 root logger 配置，确保 [chain] 链路日志在服务进程里始终可见。
logger = logging.getLogger("agent_bridge")
if not logger.handlers:
    _chain_handler = logging.StreamHandler()
    _chain_handler.setLevel(logging.INFO)
    _chain_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(_chain_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

# ---- 路径定位 ----
# 本文件：fastap2/agent_bridge/bootstrap.py
FASTAP_DIR = Path(__file__).resolve().parent.parent
# 两个项目平级：练手agent/fastap2 与 练手agent/allagent2
DEFAULT_AGENT_DIR = FASTAP_DIR.parent / "allagent2"
AGENT_DIR = Path(os.environ.get("ALLAGENT_DIR", str(DEFAULT_AGENT_DIR))).resolve()

# 结构化字段清单统一以 allagent.agent.state.PARSED_FIELDS 为准
# （仅养生养老字段，见 state.py；原旅游字段已删除）
PARSED_FIELDS = None  # 占位：在 bootstrap() 后从 state 模块导入真实清单

_BOOTED_FIELDS = []  # 真实字段清单，bootstrap 时填充


class _State:
    ready: bool = False
    agent: Any = None
    graph_mod: Any = None
    tools_count: int = 0
    error: BaseException | None = None


_state = _State()

# 【健壮性】首次引导锁：服务启动或首批并发请求可能同时触发 bootstrap，
# 不加锁会重复加载模型、重复编译 graph，甚至产生相互覆盖的中间状态。
_BOOT_LOCK = threading.Lock()


def _load_envs() -> None:
    from dotenv import load_dotenv

    # Agent：LLM key/base_url、天气 key（allagent2/core/key.env）
    load_dotenv(AGENT_DIR / "core" / "key.env")
    # 后端：MySQL 与 JWT（fastap2）
    load_dotenv(FASTAP_DIR / "database" / "mysql.env")
    load_dotenv(FASTAP_DIR / "core" / "key.env")


def _register_packages() -> None:
    agent_path = str(AGENT_DIR)
    fastap_path = str(FASTAP_DIR)
    # 先清理本引导可能已加入的条目，保证最终顺序确定
    for p in (fastap_path, agent_path):
        while p in sys.path:
            sys.path.remove(p)
    # 最终顺序：[fastap_path, agent_path, ...]
    # 两个项目都含顶层 core/database 包，必须让 fastap2 的优先；
    # 而 `session` 仅 allagent2 提供，fastap2 没有，仍会在其后的 agent_path 找到。
    sys.path.insert(0, agent_path)
    sys.path.insert(0, fastap_path)
    # allagent2 目录以包名 allagent 注册（其内部导入均为 allagent.xxx）
    if "allagent" not in sys.modules:
        pkg = types.ModuleType("allagent")
        pkg.__path__ = [agent_path]  # type: ignore[attr-defined]
        pkg.__package__ = "allagent"  # type: ignore[attr-defined]
        sys.modules["allagent"] = pkg


def _inject_backend_tools() -> int:
    # 必须在 import allagent.agent.graph 之前完成：
    # graph 顶层 create_tool_model 内部会 model.bind_tools(tools)。
    from .backend_tools import get_backend_tools

    tool_mod = importlib.import_module("allagent.tools.tool")
    added = 0
    for t in get_backend_tools():
        if t.name not in tool_mod.tools_name:
            tool_mod.tools.append(t)
            tool_mod.tools_name[t.name] = t
            added += 1
    _state.tools_count = len(tool_mod.tools)
    return added


def bootstrap() -> _State:
    """执行一次完整接线；重复调用直接返回（幂等，且线程安全）。"""
    if _state.ready:
        return _state
    # 【健壮性】加锁 + 双检：第一个发现未就绪的线程进入临界区完成初始化，
    # 其余线程在锁外/锁内第二次检查到 ready 后直接复用，不再重复接线。
    with _BOOT_LOCK:
        if _state.ready:
            return _state
        try:
            _load_envs()
            _register_packages()
            _inject_backend_tools()
            graph_mod = importlib.import_module("allagent.agent.graph")
            from langgraph.checkpoint.memory import InMemorySaver
            # 【改进】业务字段清单以 state.py 的 PARSED_FIELDS 为准（养生养老字段已扩充）
            from allagent.agent.state import PARSED_FIELDS as _STATE_FIELDS
            global PARSED_FIELDS
            PARSED_FIELDS = list(_STATE_FIELDS)

            agent = graph_mod.make_graph().compile(checkpointer=InMemorySaver())
            _state.graph_mod = graph_mod
            _state.agent = agent
            _state.ready = True
        except BaseException as exc:  # 记录引导失败，便于 /agent/status 诊断
            _state.error = exc
            raise
    return _state


def get_status() -> Dict[str, Any]:
    return {
        "ready": _state.ready,
        "agent_dir": str(AGENT_DIR),
        "tools_count": _state.tools_count,
        "error": repr(_state.error) if _state.error else None,
    }


def _summarize_message(msg: Any) -> Dict[str, Any]:
    """把一条消息压缩成可在 trace 中展示的结构。"""
    mtype = getattr(msg, "type", msg.__class__.__name__)
    content = getattr(msg, "content", "")
    if not isinstance(content, str):
        content = str(content)
    item: Dict[str, Any] = {"role": mtype, "text": content[:150]}
    tool_calls = getattr(msg, "tool_calls", None)
    if tool_calls:
        item["tool_calls"] = [
            {"name": c.get("name"), "args": c.get("args")} for c in tool_calls
        ]
    return item


class _Tracer:
    """【改进】trace 标注节点名：优先取 state.phase（intent_plan / rag_retrieval /
    llm_reasoning / tool_calling / finalizing），缺失时按旧拓扑推断。
    """

    def __init__(self) -> None:
        self.step = 0
        self.phase = "intent_plan"
        self.prev_count = 0

    def observe(self, chunk: Dict[str, Any]) -> Dict[str, Any]:
        node = chunk.get("phase") or self.phase
        self.step += 1
        messages = chunk.get("messages", [])
        total = len(messages)
        record = {
            "step": self.step,
            "node": node,
            "messages_total": total,
            "new_messages": [
                _summarize_message(m) for m in messages[self.prev_count:]
            ],
            "fields": {
                f: chunk.get(f) for f in PARSED_FIELDS if chunk.get(f) is not None
            },
        }
        self.prev_count = total
        # 无 phase 时的兜底推断（与 graph 拓扑一致）
        if node == "intent_plan":
            self.phase = "first_llm_call"
        elif node == "first_llm_call":
            last = messages[-1] if messages else None
            self.phase = "tool_use" if getattr(last, "tool_calls", None) else "end"
        elif node == "tool_use":
            self.phase = "first_llm_call"
        return record


def run_agent(
    question: str,
    thread_id: str = "default",
    debug: bool = False,
    elder_id: str | None = None,
    permissions: dict | None = None,
) -> Dict[str, Any]:
    """同步执行一次完整 Agent 流程，调用步骤与 graph.py 交互入口完全一致。

    【改进】新增权限上下文注入：
    - permissions：外部传入 PermissionContext 字段（如 allowed_elder_ids 限制访问范围）
    - elder_id：未传 permissions 时，默认只允许访问该老人数据
    debug=True 时，额外在返回值中给出每一步的执行轨迹 trace。
    """
    bootstrap()
    from langchain.messages import HumanMessage, SystemMessage
    from allagent.agent.state import PermissionContext

    graph_mod = _state.graph_mod
    first_system = SystemMessage(
        content="你只需要根据用户的问题，然后根据已经定义的结构，回复结构内部字段内部，哪些是需要后续工具查询的得到的，哪些是你直接输出的"
    )
    user_input = [HumanMessage(content=question), first_system]

    # 【改进】权限上下文：外部注入 > elder_id 推断 > 默认（不限定）
    init_state: Dict[str, Any] = {"messages": user_input}
    if permissions is not None:
        init_state["permissions"] = PermissionContext(**permissions)
    elif elder_id is not None:
        init_state["permissions"] = PermissionContext(allowed_elder_ids=[elder_id])

    configurable: Dict[str, Any] = {"thread_id": thread_id}
    if elder_id:
        configurable["current_elder_id"] = elder_id
    config = {"configurable": configurable}

    # 【修复】不再用 stream(values) 拿结果：
    # LangGraph 1.2.x 中 stream(values) 输出的是 checkpoint 包装 {type,ns,data,interrupts}，
    # 且 data 只含 output_schema（ParsedOutput）的字段，intent/phase/tool_results/messages 被过滤。
    # 改为：invoke 一次跑完整链路 → get_state 从 checkpoint 读取"完整最终 state"（全字段），
    # 元数据不再丢失；debug trace 用 get_state_history 组装，不额外调用 LLM。
    _state.agent.invoke(init_state, config=config)

    snap = _state.agent.get_state(config)
    values = snap.values
    final: Dict[Any, Any] = values.model_dump() if hasattr(values, "model_dump") else dict(values)

    messages = final.get("messages", [])
    # 【修复】answer 组装兜底：优先 final_output 的结构化 answer；
    # 缺失时只回退"最后一条 AI 消息"（绝不能取 system 消息冒充答案）；
    # 再缺失则给明确占位提示。
    answer = final.get("answer")
    if not answer:
        for m in reversed(messages):
            if getattr(m, "type", "") == "ai" and getattr(m, "content", ""):
                answer = m.content
                break
    if not answer:
        answer = "（智能体已完成本轮解析，但未生成可展示的最终回复，请换个问法重试）"
    structured = {field: final.get(field) for field in PARSED_FIELDS}

    # 【安全】链路过程只进日志，不回传前端：
    # query/intent/phase/next_need/tool_results 等元数据 → 一行汇总日志
    logger.info(
        "[chain] 完整链路结果: intent=%s phase=%s query=%s next_need=%s tool_results=%s",
        final.get("intent"),
        final.get("phase"),
        final.get("query"),
        final.get("next_need"),
        final.get("tool_results"),
    )
    if debug:
        # 【安全】debug 不再返回 trace，只把逐步执行轨迹打到日志（节点/消息/字段变化）
        step = 0
        prev_count = 0
        for h in reversed(list(_state.agent.get_state_history(config))):
            hv = h.values
            hd = hv.model_dump() if hasattr(hv, "model_dump") else dict(hv)
            step += 1
            msgs = hd.get("messages", [])
            total = len(msgs)
            logger.info(
                "[chain] step%d node=%s messages_total=%d new_messages=%s fields=%s",
                step,
                hd.get("phase") or ("start" if step == 1 else f"step{step}"),
                total,
                [_summarize_message(m) for m in msgs[prev_count:]],
                {f: hd.get(f) for f in PARSED_FIELDS if hd.get(f) is not None},
            )
            prev_count = total

    # 【安全】对外只返回智能体的最终回答 + 结构化业务字段；
    # 前端看不到任何后端链路过程（query/intent/phase/next_need/tool_results/trace 一律不进响应）
    return {
        "answer": answer,
        "structured": structured,
        "thread_id": thread_id,
    }
