"""会话配置辅助模块。

补全 agent/graph.py 顶层的 `from session.memory import make_config` 依赖。
该函数仅在「直接运行 graph.py 的交互入口」时使用；通过 FastAPI 集成
调用时，RunnableConfig 由 fastap2 的 agent_bridge 统一生成。
"""
from typing import Any, Optional

from pydantic import BaseModel


def make_config(config: Optional[Any] = None) -> dict:
    """把 config_schema(...) 转换成 LangGraph 所需的 RunnableConfig。

    LangGraph 在调用 graph.ainvoke / stream 时需要形如
        {"configurable": {"thread_id": "...", ...}}
    的配置；这里把 config_schema 中的字段原样放入 configurable。

    【改进】config_schema 已升级为 Pydantic BaseModel，这里适配：
    BaseModel 用 model_dump() 取出字段，普通映射走 dict()。
    """
    configurable: dict = {}
    if isinstance(config, BaseModel):
        # Pydantic：跳过 None 字段，保持 config 精简
        configurable.update(config.model_dump(exclude_none=True))
    elif config is not None:
        try:
            configurable.update(dict(config))
        except (TypeError, ValueError):
            # 兜底：config_schema 不是标准映射时也不要让入口崩溃
            configurable["raw"] = config
    return {"configurable": configurable}
