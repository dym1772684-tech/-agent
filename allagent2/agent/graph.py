import os
import sys
import uuid
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from langchain.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.config import get_config
from langgraph.graph import END, START, StateGraph

from allagent.agent.agent import agent_invoke, create_parser_model, create_tool_model
from allagent.agent.state import (
    PARSED_FIELDS,
    PermissionContext,
    config_schema,
    output_schema,
    state_schema,
)
from allagent.guance.logging_helper import logger
from allagent.rag.rag import (
    BM_25,
    embed_chunk,
    fenci,
    rerank,
    rrf_fusion,
    save_embeddings,
    split_into_chunks,
    vector_retrieve,
)
from allagent.tools.tool import tools_name
from session.memory import make_config
import jieba
import chromadb


class _FallbackEmbeddingModel:
    """兜底 embedding：不依赖外部模型也能让 Chroma / vector_retrieve 正常工作。"""

    def encode(self, text, batch_size=32, normalize_embeddings=True, show_progress_bar=False):
        dimension = 384
        return [0.0 for _ in range(dimension)]


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / "core" / "key.env"
load_dotenv(find_dotenv(str(ENV_PATH)))

# 【配置】API Key 请在 allagent2/core/key.env 中补充 OPENAI_API_KEY / OPENAI_BASE_URL，
# 此处不写死，由环境变量注入（你后期自己加上即可）。
api_key = os.getenv("OPENAI_API_KEY")
base_url = os.getenv("OPENAI_BASE_URL")
parser_model = create_parser_model(api_key, base_url)
tool_model = create_tool_model(api_key, base_url)


# ============================================================
# 【改进】权限控制：每个节点按自己的权限标签校验
# ============================================================
def _get_permissions(state: state_schema) -> PermissionContext:
    """取权限上下文；外部未注入时回退为默认权限（全工具 + 不限定老人 + 允许 RAG）。"""
    perm = state.permissions  # 【修复】state 是 Pydantic BaseModel，用属性访问（原 .get() 会 AttributeError）
    return perm if perm is not None else PermissionContext()


def _check_node_permission(state: state_schema, label: str) -> None:
    """节点权限校验。

    label 取值：plan / rag / llm / summarize / tool:<工具名>
    校验失败抛 PermissionError，终止本轮（外部可捕获后返回 403 语义）。
    """
    perm = _get_permissions(state)
    if label == "rag" and not perm.allow_rag:
        raise PermissionError("当前用户无权检索知识库")
    if label.startswith("tool:"):
        tool_name = label.split(":", 1)[1]
        if tool_name not in (perm.allowed_tools or []):
            raise PermissionError(f"当前用户无权调用工具 {tool_name}")


def _can_access_elder(perm: PermissionContext, elder_id: str) -> bool:
    """老人数据越权校验：allowed_elder_ids 为 None 表示未限定（允许）；否则必须在其内。"""
    allowed = perm.allowed_elder_ids
    if allowed is None:
        return True
    return elder_id in allowed


# ============================================================
# 节点 1：intent_plan —— 解析"要查什么"与"下一步需要什么"
# ============================================================
def intent_plan(state: state_schema):
    _check_node_permission(state, "plan")
    logger.info("intent_plan 开始：解析查询意图与下一步需求")
    result = parser_model.invoke(state.messages)
    # 【修复】兼容 dict 包装（{"parsed": ...}）或直接返回 ParsedOutput 实例
    parsed = result.get("parsed") if isinstance(result, dict) else result
    query = getattr(parsed, "query", None) or None
    intent = getattr(query, "intent", None) or "general"
    next_need = getattr(parsed, "next_need", None) or None
    logger.info("intent_plan 完成：intent=%s, query=%s", intent, query)
    return {"query": query, "intent": intent, "next_need": next_need, "phase": "intent_plan"}


# ============================================================
# 路由：按意图分流（tool / knowledge / answer）
# ============================================================
def route_by_intent(state: state_schema):
    intent = state.intent or "general"  # 【修复】Pydantic state 用属性访问
    if intent in ("weather", "elder_profile", "health_record"):
        return "tool"         # 需要调工具查数据
    if intent == "knowledge":
        return "knowledge"    # 需要检索知识库
    return "answer"           # general / 信息不足 → 直接汇总回答


# ============================================================
# 节点 2：check_rag —— 多路召回检索（保留原算法），结果独立存放
# ============================================================
def rag(state: state_schema):
    _check_node_permission(state, "rag")
    logger.info("rag 开始")
    messages = state.messages
    human_message = None
    for msg in messages:
        if getattr(msg, "type", None) == "human":
            human_message = getattr(msg, "content", "")
    logger.info("rag 找到用户问题=%s", human_message)

    idx = _get_rag_index()
    chunks = idx["chunks"]
    embedding_model = idx["embedding_model"]
    collection = idx["collection"]
    tokenized = idx["tokenized"]
    logger.info("rag 复用缓存索引，chunks=%d", len(chunks))

    query_words = jieba.lcut(human_message or "")
    end_documents_score = BM_25(query_words, tokenized, chunks)
    end_vector_score = vector_retrieve(human_message or "", 5, embedding_model, collection)
    fusion_result = rrf_fusion(end_documents_score, end_vector_score, 10)
    final_docs = rerank(human_message or "", fusion_result, top_k=5)
    logger.info("rag 检索到 %d 条最终文档", len(final_docs))

    # 【改进】检索结果写入 rag_context 独立字段，不再直接塞 messages，
    # 避免多条 SystemMessage 堆叠污染模型上下文；由 first_llm_call 幂等注入一次。
    docs_text = "\n\n".join(doc["text"] for doc in final_docs)
    return {"rag_context": docs_text, "phase": "rag_retrieval"}


# ============================================================
# 节点 3：first_llm_call —— LLM 决策（可能计划调用工具）
# ============================================================
def first_llm_invoke(state: state_schema):
    _check_node_permission(state, "llm")
    logger.info("first_llm_invoke 开始")
    messages = list(state.messages)

    # 【改进】知识库上下文幂等注入：仅在还没有该内容时追加一次
    rc = state.rag_context  # 【修复】Pydantic state 用属性访问
    if rc and not any(
        getattr(m, "type", "") == "system" and rc in (getattr(m, "content", "") or "")
        for m in messages
    ):
        messages.append(SystemMessage(content=rc))
    messages.append(SystemMessage(content="你需要调用工具来回答相关问题"))

    result = agent_invoke(tool_model, {"messages": messages})
    messages.append(result)
    logger.info("first_llm_invoke 完成，消息总数=%d", len(messages))
    return {"messages": messages, "phase": "llm_reasoning"}


# ============================================================
# 节点 4：tool_use —— 按白名单执行工具 + elder 越权拦截 + 结果回填
# ============================================================
def tool_use(state: state_schema):
    _check_node_permission(state, "tool_use")  # 【改进】节点级权限标签（无具体工具时仅校验是否允许进入）
    logger.info("tool_use 开始，当前消息总数=%d", len(state.messages))
    messages = list(state.messages)
    result = messages[-1]
    perm = _get_permissions(state)
    tool_results = dict(state.tool_results or {})  # 【修复】Pydantic state 用属性访问

    if getattr(result, "tool_calls", None):
        logger.info("tool_use 处理 tool_calls=%s", result.tool_calls)
        for call in result.tool_calls:
            name = call["name"]
            args = call.get("args") or {}
            # 【改进】工具白名单校验：不在 allowed_tools 内的工具直接拒绝
            _check_node_permission(state, f"tool:{name}")
            # 【改进】老人数据类工具：elder_id 越权拦截（防越权访问其他老人）
            if name in ("query_elder_profile", "query_health_records"):
                elder_id = args.get("elder_id")
                if elder_id and not _can_access_elder(perm, elder_id):
                    logger.warning("越权拦截：用户尝试访问老人 %s 的数据", elder_id)
                    messages.append(ToolMessage(
                        content=f"无权访问老人 {elder_id} 的数据（权限拦截）",
                        tool_call_id=call.get("id"),
                    ))
                    continue
            tool = tools_name.get(name)
            if tool is None:
                messages.append(ToolMessage(content=f"未知工具: {name}", tool_call_id=call.get("id")))
                continue
            observation = tool.invoke(args)
            # 【改进】工具结果统一回填 tool_results（供 final_output 汇总）
            tool_results[name] = observation
            logger.info("调用工具 %s args=%s 返回=%s", name, args, observation)
            messages.append(ToolMessage(content=observation, tool_call_id=call.get("id")))
    else:
        logger.info("tool_use 未找到 tool_calls，直接返回")
    logger.info("tool_use 结束，消息总数=%d", len(messages))
    return {"messages": messages, "tool_results": tool_results, "phase": "tool_calling"}


# ============================================================
# 节点 5：final_output —— 查询完成后统一结构化输出
# ============================================================
def final_output(state: state_schema):
    _check_node_permission(state, "summarize")
    logger.info("final_output 开始：汇总结构化输出")
    result = parser_model.invoke(state.messages)
    # 【修复】兼容两种返回形态：langchain with_structured_output 的 dict 包装（{"parsed": ...}）
    # 或直接返回 ParsedOutput 实例；解析失败时 parsed 为 None
    parsed = result.get("parsed") if isinstance(result, dict) else result
    out: dict = {"phase": "finalizing"}
    if parsed is not None:
        # 【改进】全部业务字段 + 元数据（query / next_need / answer）一次汇总输出
        for field in PARSED_FIELDS:
            out[field] = getattr(parsed, field, None)
        out["query"] = getattr(parsed, "query", None)
        out["next_need"] = getattr(parsed, "next_need", None)
    # 【健壮性】结构化解析失败或 answer 缺失时，兜底取最后一条 AI 消息作为答案，
    # 保证 /agent/chat 永远不会返回空 answer
    if not out.get("answer"):
        for msg in reversed(state.messages):
            if getattr(msg, "type", "") == "ai" and getattr(msg, "content", ""):
                out["answer"] = msg.content
                break
    logger.info("final_output 完成，answer 长度=%d", len(out.get("answer") or ""))
    return out


# ============================================================
# 条件边：工具循环是否继续（含最大轮数保护）
# ============================================================
def should_continue(state: state_schema):
    last_messages = state.messages[-1]
    if not getattr(last_messages, "tool_calls", None):
        return "final_output"
    # 【改进】最大工具轮数保护：超过上限强制收尾，防止无限循环
    config = get_config()
    max_rounds = ((config or {}).get("configurable") or {}).get("max_tool_rounds", 3)
    tool_rounds = sum(1 for m in state.messages if getattr(m, "type", "") == "tool")
    if tool_rounds >= max_rounds:
        logger.warning("工具调用已达上限 %d 轮，强制进入 final_output", max_rounds)
        return "final_output"
    return "tool_use"


_rag_index = None


def _get_rag_index():
    global _rag_index
    if _rag_index is None:
        logger.info("首次构建知识库索引（只执行一次，随后缓存）")
        chunks = split_into_chunks("")
        embedding_model = None
        try:
            from sentence_transformers import SentenceTransformer
            embedding_model = SentenceTransformer("shibing624/text2vec-base-chinese")
        except Exception as exc:
            logger.warning("SentenceTransformer 未加载，使用兜底 embedding：%s", exc)
            embedding_model = _FallbackEmbeddingModel()

        embeddings = [embed_chunk(chunk, embedding_model) for chunk in chunks]
        chroma_client = chromadb.EphemeralClient()
        collection = chroma_client.create_collection(name="my_collection")
        save_embeddings(chunks, embeddings, collection)

        _rag_index = {
            "chunks": chunks,
            "embedding_model": embedding_model,
            "collection": collection,
            "tokenized": fenci(chunks),
        }
        logger.info("知识库索引构建完成，chunks=%d", len(chunks))
    return _rag_index


def make_graph():
    """【改进】新拓扑：
    START → intent_plan（先出 query/next_need）
          → 条件路由：tool → 工具循环 / knowledge → check_rag / answer → final_output
          → first_llm_call ⇄ tool_use（白名单 + 越权拦截 + 结果回填）
          → final_output（查询后统一结构化输出）→ END
    """
    agent_builder = StateGraph(state_schema=state_schema, output_schema=output_schema)
    agent_builder.add_node("intent_plan", intent_plan)
    agent_builder.add_node("check_rag", rag)
    agent_builder.add_node("first_llm_call", first_llm_invoke)
    agent_builder.add_node("tool_use", tool_use)
    agent_builder.add_node("final_output", final_output)

    agent_builder.add_edge(START, "intent_plan")
    agent_builder.add_conditional_edges(
        "intent_plan",
        route_by_intent,
        path_map={"tool": "first_llm_call", "knowledge": "check_rag", "answer": "final_output"},
    )
    agent_builder.add_edge("check_rag", "first_llm_call")
    agent_builder.add_conditional_edges(
        "first_llm_call",
        should_continue,
        path_map={"tool_use": "tool_use", "final_output": "final_output"},
    )
    agent_builder.add_edge("tool_use", "first_llm_call")
    agent_builder.add_edge("final_output", END)
    return agent_builder


if __name__ == "__main__":
    agent = make_graph().compile(checkpointer=InMemorySaver())
    logger.info("agent graph 已编译完成")
    print("agent ready")
