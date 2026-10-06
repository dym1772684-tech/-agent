"""Agent 对话接口的请求 / 响应 schema。

【安全改造】对外响应只包含智能体的最终回答 + 结构化业务字段；
query / intent / phase / next_need / tool_results / trace 等链路过程
一律不进 HTTP 响应，只写入服务日志（见 bootstrap.run_agent）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AgentChatRequest(BaseModel):
    message: str = Field(..., description="向养老智能体提出的问题")
    elder_id: Optional[str] = Field(
        default=None, description="可选，老人编号，用于隔离会话与定位档案"
    )
    thread_id: Optional[str] = Field(
        default=None, description="可选，会话线程ID；不传则用 elder_id 或自动生成"
    )
    debug: bool = Field(
        default=False, description="为true时在服务日志中输出逐步执行轨迹（不返回前端）"
    )
    allowed_elder_ids: Optional[List[str]] = Field(
        default=None,
        description="【改进】权限：限定本请求可访问的老人编号范围；None=不限定（由后端鉴权层注入）",
    )
    allowed_tools: Optional[List[str]] = Field(
        default=None,
        description="【改进】权限：限定本请求可调用的工具白名单；None=使用默认白名单",
    )


class AgentChatData(BaseModel):
    answer: str = Field(..., description="智能体最终自然语言回复（前端唯一可见的链路产物）")
    structured: Dict[str, Any] = Field(
        default_factory=dict,
        description="结构化输出字段（养生养老维度：health_advice/diet_advice/exercise_advice/medication_advice/risk_level/emergency_flag，见 state.PARSED_FIELDS）",
    )
    thread_id: str = Field(..., description="本次会话线程ID，可用于多轮对话")
