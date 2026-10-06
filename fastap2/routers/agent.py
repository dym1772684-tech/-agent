"""养老智能体对话路由：把 HTTP 请求桥接到 LangGraph Agent。

【安全改造】本路由不写任何安全逻辑，只调用 agent_bridge.middleware 的
AgentSecurityService 门面：
- build_permissions：登录用户 → 权限上下文（admin 可看敏感，common 脱敏受限）
- guard_message：入口敏感阻断（命中且无权限 → 直接阻断，不进智能体链路）
- enter_context / exit_context：线程级鉴权上下文注入/清理（DB 网关依赖）
"""
import uuid

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool

from agent_bridge import get_status, run_agent
from agent_bridge.middleware import AgentSecurityService
from agent_bridge.schemas import AgentChatRequest
from core.responses import ApiResponse
from core.settings import CurrentUser

agent_router = APIRouter(prefix="/agent", tags=["养老智能体对话"])


@agent_router.post("/chat")
async def chat_with_agent(req: AgentChatRequest, current: CurrentUser):
    # 【鉴权】权限上下文全部由安全服务门面生成（JWT 登录用户 + 请求约束）
    permissions = AgentSecurityService.build_permissions(
        current, req.allowed_elder_ids, req.allowed_tools
    )
    # 【安全】入口敏感阻断：命中且无权限 → 不进入智能体链路
    guard = AgentSecurityService.guard_message(req.message, permissions)
    if guard is not None:
        return ApiResponse.fail(code=guard["code"], msg=guard["msg"])

    # 会话线程：优先显式 thread_id，其次 elder_id，最后自动生成
    thread_id = req.thread_id or req.elder_id or f"t-{uuid.uuid4().hex[:12]}"
    # 【鉴权】注入线程级上下文（供 DB 网关读取），执行完清理
    AgentSecurityService.enter_context(permissions)
    try:
        # graph 为同步且 RAG 计算较重，放到线程池执行，避免阻塞事件循环
        result = await run_in_threadpool(
            run_agent, req.message, thread_id, req.debug, req.elder_id, permissions
        )
    finally:
        AgentSecurityService.exit_context()
    return ApiResponse.success(data=result)


@agent_router.get("/status")
async def agent_status():
    # 诊断：接线是否完成、注册到的工具数量、allagent2 路径
    return ApiResponse.success(data=get_status())
