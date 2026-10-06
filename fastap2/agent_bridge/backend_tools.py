"""把 fastap2 后端的业务能力封装成 LangChain 工具，供 Agent 调用。

【安全改造】智能体不能再自己调用数据库：
- 原直连 MySQL 的逻辑（engine / Session / 查询）已整体迁移到 agent_bridge/middleware.py
  的 DBAccessMiddleware（唯一允许访问数据库的组件）。
- 这里的数据库工具函数变成“薄壳”，只负责参数绑定，实际执行一律转发给
  DBAccessMiddleware.execute()：网关内部完成 鉴权 → 查询 → 敏感扫描 → JSON 返回。
- 非数据库工具（calculator / get_real_weather）不受影响，仍在 allagent2 侧。

LangGraph 中工具是「同步」invoke 的；表映射复用 models 中已有的类。
"""
from __future__ import annotations

from typing import Optional

from langchain.tools import tool
from pydantic import BaseModel, Field

# 【安全】统一数据访问网关：本模块不再 import sqlalchemy / 持有任何 DB 连接；
# 对外统一走 AgentSecurityService 安全服务门面（鉴权+敏感扫描+JSON 全在 middleware 内部）
from .middleware import AgentSecurityService


class ElderQuery(BaseModel):
    elder_id: str = Field(description="老人唯一编号")


class HealthQuery(BaseModel):
    elder_id: str = Field(description="老人唯一编号")
    metric_type: Optional[str] = Field(
        default=None, description="指标类型，如血压/血糖/心率；不填则返回最新的全部记录"
    )


@tool(
    "query_elder_profile",
    description="根据老人编号查询老人档案：姓名、年龄、性别、自理状态、慢性病、联系电话；查不到会提示无记录",
    args_schema=ElderQuery,
)
def query_elder_profile(elder_id: str) -> str:
    """【安全】薄壳：不直接访问数据库，统一走 AgentSecurityService 安全服务（鉴权+敏感扫描+JSON）。"""
    return AgentSecurityService.query_elder_profile_safe(elder_id)


@tool(
    "query_health_records",
    description="根据老人编号查询其最新健康监测记录（指标类型、数值、记录时间），最多返回10条",
    args_schema=HealthQuery,
)
def query_health_records(elder_id: str, metric_type: Optional[str] = None) -> str:
    """【安全】薄壳：不直接访问数据库，统一走 AgentSecurityService 安全服务（鉴权+敏感扫描+JSON）。"""
    return AgentSecurityService.query_health_records_safe(elder_id, metric_type)


def get_backend_tools():
    """供 bootstrap 注入的后端工具列表。"""
    return [query_elder_profile, query_health_records]
