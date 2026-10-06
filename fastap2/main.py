# main.py
from fastapi import FastAPI
from fastapi.responses import FileResponse
from database.database import Base, engine
from routers.health import router
from routers.elder import elder_router
from models.elder import Elder
import uvicorn
from models.health import HealthRecord,HealthRisk
from routers.users import user_router
from routers.agent import agent_router
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# 启动自动创建不存在的表；已经存在不会覆盖
async def init_db():
    async with engine.begin() as conn:
        # run_sync包装同步建表DDL
        await conn.run_sync(Base.metadata.create_all)

app = FastAPI(title="养老智能体")
app.include_router(user_router,prefix="/api/v1")
app.include_router(router, prefix="/api/v1")
app.include_router(elder_router,prefix="/api/v1")
app.include_router(agent_router,prefix="/api/v1")

@app.get("/")
async def index_page():
    return FileResponse(BASE_DIR / "dashboard.html")

@app.get("/dashboard")
async def dashboard_page():
    return FileResponse(BASE_DIR / "dashboard.html")

if __name__=="__main__":
    uvicorn.run("main:app",
                host="127.0.0.1",
                port=8000,
                reload=True
                )#uvicorn ft:app --reload命令行启动

