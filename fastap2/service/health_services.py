from models.health import  HealthRecord
from database.database import AsyncSession,Session
from datetime import datetime
from sqlalchemy import select
from models.elder import Elder
from database.database import Base
from core.responses import ApiResponse
from schemas.health import HealthRecord_create
async def get_record(id:str,db:AsyncSession):
    mission=select(HealthRecord).where(HealthRecord.id==id)
    result=await db.execute(mission)
    record=result.scalar_one_or_none()
    return record
async def create_record(db:AsyncSession,obj_in:HealthRecord_create):
    mission=select(HealthRecord).where(HealthRecord.id==obj_in.health_id)
    orm_result=await db.execute(mission)
    result=orm_result.scalar_one_or_none()
    if result :
        raise ApiResponse.fail(code=409,msg="not")
    new_HealthRecord=HealthRecord(
        id=obj_in.health_id,
        elder_id=obj_in.elder_id,
        metric_type=obj_in.metric_type,
        value=obj_in.value,
        create_time=datetime.now()
    )
    db.add(new_HealthRecord)
    await db.commit()
    await db.refresh(new_HealthRecord)
    return ApiResponse.success(data=new_HealthRecord)
async def delete_record(db:AsyncSession,obj_in:HealthRecord_create):
    mission=select(HealthRecord).where(HealthRecord.elder_id==obj_in.elder_id)
    orm_result=await db.execute(mission)
    result=orm_result.scalar_one_or_none()
    if result:
        await db.delete(result)  # 【修复】AsyncSession.delete 是 async 方法，原代码漏 await 导致删除从未执行
    else:
        return ApiResponse(code=404,description="资源不存在")
    await db.commit()
    return "成功删除"
async def update_record(db:AsyncSession,obj_in:HealthRecord_create):
    mission=select(HealthRecord).where(HealthRecord.elder_id==obj_in.health_id)
    orm_result=await db.execute(mission)
    result=orm_result.scalar_one_or_none()
    if  not result:
        raise ApiResponse.fail(code=404,description="资源未创建")
    if result.risk_content!=obj_in.risk_content:
        result.risk_content=obj_in.risk_content
    await db.commit()
    await db.refresh(result)

