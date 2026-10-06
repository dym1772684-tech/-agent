from pydantic import BaseModel, Field
from typing import Optional

# 创建老人档案 入参
class ElderCreate(BaseModel):
    elder_id: str = Field(..., description="老人唯一编号")
    name: str
    age: Optional[int] = None
    gender: Optional[str] = None
    health_tag: Optional[str] = None
    chronic_disease: Optional[str] = None
    phone: Optional[str] = None
class ElderUpdate(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    health_tag: Optional[str] = None
    chronic_disease: Optional[str] = None
    phone: Optional[str] = None