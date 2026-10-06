# 养老智能体 集成说明（fastap2 × allagent2 串联）

## 一、串联目标与原则

- **fastap2**：分层清晰的 FastAPI 养老后端（routers / service / models / schemas / database / core）。
- **allagent2**：LangGraph 智能体（RAG 多路召回 + 工具调用），其内部包名前缀为 `allagent.`。
- 原则：**不改变两个项目各自的业务思想与实现**，只新增一层「胶水层」把两者打通，并对少量「不改就无法导入/运行」的硬编码做最小修复。

---

## 二、改动清单

### A. allagent2 —— 仅 3 处最小适配（逻辑/算法均未改）

1. **新增 `session/__init__.py`、`session/memory.py`**
   `agent/graph.py` 顶层有 `from session.memory import make_config`，但该模块原本缺失，会导致 graph 无法导入。补上一个把 `config_schema` 转成 `{"configurable": {...}}` 的 `make_config`。

2. **修复 `rag/rag.py` 中 `split_into_chunks` 的文件路径**
   原实现硬编码打开 `...\allagent\rag\information.md`（该路径不存在，且传入参数 `doc_file` 被忽略）。改为基于 `__file__` 定位同目录真实的 `information.md`；**读取与按 `\n\n` 切分的逻辑完全不变**。

3. **`agent/graph.py`：底部交互循环加入口保护**
   将原本模块顶层、导入即执行的 `while True:` 交互循环整体包进 `if __name__ == "__main__":`。节点定义、图结构、stream 参数等**一字未改**，只是让该模块能被 FastAPI 安全导入。

### B. fastap2 —— 新增集成层 + 两行接线（原有代码逻辑未动）

1. **新增 `agent_bridge/`（胶水层）**
   - `bootstrap.py`：加载两个项目的 `.env`；用 `sys.path` + `importlib` 把 allagent2 目录以包名 **`allagent`** 注册（无需改动其内部 `allagent.xxx` 导入）；在导入 graph 前**动态注入后端工具**；编译 LangGraph；提供 `run_agent()`。
   - `backend_tools.py`：把后端能力封装成两个**只读** LangChain 工具 `query_elder_profile`、`query_health_records`，使用独立的**同步** SQLAlchemy engine（pymysql），与 FastAPI 请求级 AsyncSession 解耦。
   - `schemas.py`：对话请求/响应的 Pydantic 模型。
   - `__init__.py`：导入即完成一次接线（幂等）。

2. **新增 `routers/agent.py`**：暴露 `POST /agent/chat`、`GET /agent/status`。

3. **`main.py` 仅增加两行**：`from routers.agent import agent_router` 与 `app.include_router(agent_router, prefix="/api/v1")`。

4. **新增 `run_server.py`（一键启动，不依赖当前工作目录）、`requirements.txt`（依赖清单）**。

---

## 三、整体架构与两条数据流

- **业务 CRUD 链路（原有，不变）**：客户端 → `routers(users/health/elder)` → `service` → 异步 SQLAlchemy（aiomysql）→ MySQL。
- **智能对话链路（新增）**：客户端 `POST /api/v1/agent/chat` → `routers/agent`（`run_in_threadpool` 放线程池）→ `agent_bridge.run_agent` → LangGraph：
  `check_rag`（BM25 + 向量召回 + RRF 融合 + CrossEncoder 重排）→ `first_llm_call`（tool_model 决策）→ 按需 `tool_use` 调用工具后回到 `first_llm_call`，否则结束。
  - 工具共 **4 个**：原有 `calculator`、`get_real_weather`，以及新增的 `query_elder_profile`、`query_health_records`。
  - 后两者通过同步 engine **回查后端 MySQL 的老人档案 / 健康记录**，实现「Agent ↔ 后端数据」的反向打通。
  - 返回：`answer`（最终自然语言）+ `structured`（人数/评级/天气/方案/酒店/销售 6 个结构化字段）+ `thread_id`（可用于多轮）。

> 架构分层与连接关系的可视化图，见本次对话中直接渲染的架构图。

---

## 四、启动方式

推荐（使用已装好依赖的解释器，且不依赖当前目录）：

```powershell
E:\python\python.exe C:\Users\17726\Desktop\练手agent\fastap2\run_server.py
```

或沿用原方式：

```powershell
cd C:\Users\17726\Desktop\练手agent\fastap2
E:\python\python.exe main.py
```

启动后：
- 接口文档（Swagger）：http://127.0.0.1:8000/docs
- 智能体接线状态：http://127.0.0.1:8000/api/v1/agent/status

---

## 五、接口示例

**对话** `POST /api/v1/agent/chat`

请求体：

```json
{ "message": "帮我看看老人 E001 最近的健康情况，给点养生建议", "elder_id": "E001" }
```

返回（外层为统一 `ApiResponse`）：

```json
{
  "code": 200, "msg": "success",
  "data": {
    "answer": "……最终自然语言回复……",
    "structured": { "number_of_people": null, "grade_for_site": null, "...": "..." },
    "thread_id": "E001"
  }
}
```

`thread_id` 不传时：优先用 `elder_id`，否则自动生成；同一 `thread_id` 可承载多轮对话（checkpointer 为内存版，重启即清空）。

---

## 六、运行前置条件

1. **MySQL 已启动**，且存在 `agent_demo` 库（连接信息见 `database/mysql.env`）。智能体后端工具为只读，需要 `elder`、`health_record` 表中有数据。
2. **首次对话需联网下载本地模型**（已设置 HF 镜像 `hf-mirror.com`）：
   - embedding：`shibing624/text2vec-base-chinese`
   - rerank：`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`
   下载后会缓存，之后离线可用。注意：当前 `rag` 节点每次运行都会重新加载模型并重建临时 Chroma，耗时较长（这是原实现，未改动）。
3. **LLM Key**：已在 `allagent2/core/key.env`（DeepSeek，OpenAI 兼容接口），天气工具 key 同在该文件。
4. **Redis 非必需**：仅 `database/redistest.py` 用到。

---

## 七、本次已完成的验证

- `py_compile`：11 个新增/修改文件语法检查全部通过。
- 完整 **bootstrap**（加载 env → 注册 `allagent` 包 → 注入 4 个工具 → 导入并编译 graph）在**不联网**情况下通过；`parser/tool model` 均用真实 key 创建。
- `TestClient` 调用 `GET /api/v1/agent/status` 返回 200，`ready=true、tools_count=4`。
- **未实际发起 `/agent/chat` 推理**：该步骤会触发本地模型下载、DeepSeek API 调用（计费）与 MySQL 查询，属于运行时外部依赖，请在满足第六节条件后自行触发。

---

## 八、给 FastAPI 学习者的两个关键点

1. LangGraph 的 `stream` 是**同步阻塞**且 RAG 计算较重，路由里用 `fastapi.concurrency.run_in_threadpool` 放到线程池执行，避免阻塞 asyncio 事件循环。
2. Agent 工具运行在与请求不同的执行上下文，因此后端工具使用**独立同步 engine** 查询，而不是复用请求内的 `AsyncSession`；两者共享同一个 MySQL 数据库，互不持有对方会话。
