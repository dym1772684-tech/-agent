"""agent_bridge：把 allagent2（LangGraph 智能体）接入 fastap2（FastAPI 后端）的集成层（胶水层）。

导入该包即完成接线：加载配置 -> 注册 allagent 包 -> 注入后端工具 -> 编译 graph。
上述动作均为惰性、不在导入期联网；真正的模型推理在每次请求时发生。
"""
from .bootstrap import (
    AGENT_DIR,
    FASTAP_DIR,
    bootstrap,
    get_status,
    run_agent,
)

# 导入该包即完成一次接线（幂等）
bootstrap()

__all__ = ["bootstrap", "run_agent", "get_status", "AGENT_DIR", "FASTAP_DIR"]
