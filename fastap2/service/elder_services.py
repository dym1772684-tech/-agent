from sqlalchemy.orm import Session
from sqlalchemy import select
from models.elder import Elder
from schemas.elder import ElderCreate
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
async def create_elder(db: AsyncSession, req: ElderCreate):
    # 检查elder_id是否重复
    exist = select(Elder).where(Elder.elder_id == req.elder_id)
    orm_result=await db.execute(exist)
    result=orm_result.scalar_one_or_none()
    if result:
        raise HTTPException(status_code=400, detail="该老人ID已存在")
    new_elder = Elder(
        elder_id=req.elder_id,
        name=req.name,
        age=req.age,
        gender=req.gender,
        health_tag=req.health_tag,
        chronic_disease=req.chronic_disease,
        phone=req.phone
    )
    db.add(new_elder)
    await db.commit()
    await db.refresh(new_elder)
    return True
# 【修复】ORM 对象无法被 FastAPI 直接序列化（PydanticSerializationError），
# 统一转成 dict 再返回，select/update/list 三处同因一并修复。
def _elder_to_dict(elder: Elder) -> dict:
    return {
        "elder_id": elder.elder_id,
        "name": elder.name,
        "age": elder.age,
        "gender": elder.gender,
        "health_tag": elder.health_tag,
        "chronic_disease": elder.chronic_disease,
        "phone": elder.phone,
        "create_time": str(elder.create_time) if elder.create_time else None,
    }


async def get_elder_by_id(db: AsyncSession, elder_id: str):
    mission=select(Elder).where(Elder.elder_id==elder_id)##【修复】原误用整数主键 Elder.id 去匹配业务编号，应使用 Elder.elder_id
    orm_result=await db.execute(mission)
    result=orm_result.scalar_one_or_none()
    if not result:
        raise HTTPException(status_code=404, detail="老人不存在")
    return _elder_to_dict(result)  # 【修复】不再直接返回 ORM 对象

async def list_elder(db: AsyncSession, page:int, size:int):
    total = (await db.execute(select(func.count(Elder.id)))).scalar_one()
    stmt = select(Elder).offset((page - 1) * size).limit(size)
    data = (await db.execute(stmt)).scalars().all()
    return {
        "total": total,
        "page": page,
        "size": size,
        "list": [_elder_to_dict(e) for e in data]  # 【修复】不再直接返回 ORM 对象列表
    }

async def update_elder(db: AsyncSession, elder_id: str, req: ElderCreate):
    mission =  select(Elder).where(Elder.elder_id == elder_id)
    result =await db.execute(mission)
    elder = result.scalar_one_or_none()
    if not elder:
        raise HTTPException(status_code=404, detail="老人不存在")
    elder.name = req.name
    elder.age = req.age
    elder.gender = req.gender
    elder.health_tag = req.health_tag
    elder.chronic_disease = req.chronic_disease
    elder.phone = req.phone
    await db.commit()
    await db.refresh(elder)
    return _elder_to_dict(elder)  # 【修复】不再直接返回 ORM 对象

async def delete_elder(db: AsyncSession, elder_id: str):
    mission=select(Elder).where(Elder.elder_id==elder_id)
    result=await db.execute(mission)
    elder=result.scalar_one_or_none()
    if not elder:
        raise HTTPException(status_code=404, detail="老人不存在")
    await db.delete(elder)  # 【修复】AsyncSession.delete 是 async 方法，原代码漏 await 导致删除从未执行
    await db.commit()
    if await check_elder(db,elder_id)=="elder dosen't exist":
        return {"msg":"删除成功"}
    else :
        return {"still exist"}
async def check_elder(db:AsyncSession,elder_id:str):
    mission=select(Elder).where(Elder.elder_id==elder_id)##【修复】原误用整数主键 Elder.id 去匹配业务编号，应使用 Elder.elder_id
    if  (await db.execute(mission)).scalar_one_or_none():
        return "Elder is existing"
    else:
        return "elder dosen't exist"
    

