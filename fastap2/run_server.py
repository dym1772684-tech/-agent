"""一键启动入口（不依赖当前工作目录）。

无论从哪里运行，都会先把 fastap2 目录加入 sys.path，再导入 app
（导入 routers.agent 时会自动完成 Agent 接线），最后启动 uvicorn。

推荐用法（使用你已装好依赖的解释器）：
    E:\\python\\python.exe run_server.py
启动后访问：
    http://127.0.0.1:8000/docs            接口文档
    http://127.0.0.1:8000/api/v1/agent/status   智能体接线状态
"""
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import uvicorn  # noqa: E402
from main import app  # noqa: E402  导入即触发 agent_bridge 接线

if __name__ == "__main__":
    # 关闭 reload，避免重载子进程重复初始化 allagent2 并导致旧进程/新进程混用
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)
