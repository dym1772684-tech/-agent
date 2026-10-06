from database.database import Base
from sqlalchemy import Column, String, Text, DateTime, Integer
from datetime import  datetime
from fastapi import Depends
from database.database import Session
from core import ApiResponse
from fastapi import APIRouter
from schemas.elder import ElderCreate
from database.database import get_db
from schemas.elder import ElderUpdate

def get_now():
    return datetime.now()
class Elder(Base):
    __tablename__="elder"
    id=Column(Integer,primary_key=True,autoincrement=True)
    elder_id=Column(String(64),unique=True,index=True)
    name = Column(String(64))
    age = Column(Integer, nullable=True)
    gender = Column(String(16), nullable=True)
    health_tag = Column(String(128), nullable=True) # 自理/半失能
    chronic_disease = Column(Text, nullable=True)
    create_time = Column(DateTime, default=get_now)
    address=Column(String(64),default=None)
    phone=Column(String(64),default=None)