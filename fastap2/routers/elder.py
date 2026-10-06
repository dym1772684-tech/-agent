from core.responses import ApiResponse
from fastapi import APIRouter,Depends
from core.settings import check_jwt, require_roles  # 【鉴权】登录校验依赖 + RBAC 角色依赖
from schemas.elder import ElderCreate
from database.database import get_db
from schemas.elder import ElderUpdate
from sqlalchemy.orm import Session
from service.elder_services import (
    create_elder,
    get_elder_by_id,
    list_elder,
    update_elder,
    delete_elder
)
# 【鉴权】整组保护：该 router 下所有接口都必须先登录（缺 token / 无效 / 过期 → 401）
elder_router=APIRouter(prefix="/elder_identity",tags=["老人档案"],dependencies=[Depends(check_jwt)])
@elder_router.post("/create_elder")
async def make_elder(req: ElderCreate,
    db: Session = Depends(get_db)):
    record = await create_elder(db, req)
    return ApiResponse.success(data=record)
@elder_router.get("/select_elder")
async def select_elder(elder_id:str,db:Session=Depends(get_db)):
    elder_data=await get_elder_by_id(db,elder_id)
    return  ApiResponse.success(data=elder_data)
@elder_router.post("/update_elder")
async def update_elder_(new_Elder:ElderCreate,db:Session=Depends(get_db)):
    end_elder=await update_elder(db,new_Elder.elder_id,new_Elder)
    return end_elder
@elder_router.delete("/delete_elder")
async def delete_elder_(elder:ElderCreate,
                        current=Depends(require_roles("admin")),  # 【鉴权】删除仅限 admin：非 admin → 403
                        db:Session=Depends(get_db)):
    return await delete_elder(db,elder.elder_id)
