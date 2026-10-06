########这里做的需求是 登陆需求 首先用户发送表单 里面的字段有 password username 
"""然后我们系统要自动在login api   做到以下几点
第一  鉴定账号 密码  使用hash校验
第二   如果存在 返回jwt   jwt里面封装的内容就是他的user_id,user_role
如果不存在 就返回 账号密码输入错误"""
from sqlalchemy import Column, String, Text, DateTime, Integer
from sqlalchemy.orm import Session
from database.database import Base
import datetime
class User_table(Base):
    __tablename__="User"
    id=Column(Integer,primary_key=True,autoincrement=True)
    username=Column(String(64))
    password=Column(String(64))
    create_time=Column(DateTime,default=datetime.datetime.now)
    user_id=Column(String(64))
    user_role=Column(String(64))
from core.responses import ApiResponse
from fastapi import APIRouter
from core.settings import hash_password
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from database.database import get_db
from schemas.user import User
from models.users import User_table
from core.settings import check_password,create_access_token
from fastapi.security import OAuth2PasswordBearer
user_router=APIRouter()
oauth2_schema=OAuth2PasswordBearer(tokenUrl="login")###用来读取token
@user_router.post("/register")
async def create_User(users:User,db:AsyncSession=Depends(get_db)):
    end_password=hash_password(users.password)
    users.password=end_password
    new_user=User_table(
            username=users.username,
            password=users.password,
            user_role="common",
        )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return ApiResponse(code="200",msg="成功创建该用户")
@user_router.post("/login")
def check_user_and_give_jwt_token(users:User,db:AsyncSession=Depends(get_db)):
    if check_password(users,db):
        token_data={
        "user_id":str(users.user_id),
        "role":f"{users.role}",
        }
        token=create_access_token(token_data)
        return {"access_token":token,"token_type":"bearer"}
    else:
        return "账号或密码错误"
    