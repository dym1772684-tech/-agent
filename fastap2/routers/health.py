from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from core.responses import ApiResponse
from core.settings import check_jwt  # 【鉴权】登录校验依赖
from database.database import get_db
from schemas.health import HealthRecord_create
from service.health_services import(
get_record,
delete_record,
update_record,
create_record
)
# 【鉴权】整组保护：该 router 下所有接口都必须先登录（缺 token / 无效 / 过期 → 401）
router=APIRouter(prefix="/health",tags=['健康'],dependencies=[Depends(check_jwt)])
@router.post("/create_record")
async def post(data:HealthRecord_create,db=Depends(get_db)):
    if data:
        await create_record(db,data)
        return ApiResponse.success(msg="成功")##【修复】原 ApiResponse.success(code=200,description="成功") 中 code/description 不是 success 的参数（其签名为 data/msg），会 TypeError
    else :
        raise HTTPException(status_code=400,detail="请求结构不对")##【修复】原 raise ApiResponse(code="400",description=...) 参数无效；请求错误应抛 HTTPException
@router.get("/record/{id}")
async def get__record(id:str,db=Depends(get_db)):##【优化】补 id 的类型标注 str
    if id:
        result=await get_record(id,db)
        if result is None:##【优化】查不到时直接 404，原 model_validate(None) 会抛 ValidationError
            raise HTTPException(status_code=404,detail="资源不存在")
        end_result=HealthRecord_create.model_validate(result)
        return (end_result.model_dump())
    else :
        raise HTTPException(status_code=404,detail="资源不存在")##【修复】同上，改用 HTTPException

@router.get("/stats/{elder_id}")
def return_record():
    return {"messages"}
@router.get("/risk/{elder_id}")
def return_risk():
    return {"risk"}

##### 三个函数一次性分清
"""
1. **`model_validate(对象)`**：对象 → Pydantic 实例
2. **`model_dump()`**：Pydantic 实例 → Python 字典
3. **`model_dump_json()`**：Pydantic 实例 → JSON 字符串"""
