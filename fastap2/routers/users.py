import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.responses import ApiResponse
from core.settings import check_password, create_access_token, hash_password
from database.database import get_db
from models.users import User_table
from schemas.user import User

user_router = APIRouter()


@user_router.post("/register")
async def create_User(users: User, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User_table).where(User_table.username == users.username))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail="用户名已存在")

    end_password = hash_password(users)
    users.password = end_password
    new_user = User_table(
        username=users.username,
        password=users.password,
        user_id=str(uuid.uuid4()),
        user_role=users.role,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return ApiResponse.success(msg="成功创建该用户")


# 【鉴权】双登录端点，避免 422：
# - POST /login：JSON body（{"username","password"}）—— 你现有客户端的调用方式
# - POST /token：标准表单（OAuth2PasswordRequestForm）—— 供 /docs 右上角 Authorize 使用
# 两者共用 check_password + create_access_token，返回结构一致。


@user_router.post("/login")
async def login_json(
    users: User,  # JSON body：{"username": "...", "password": "..."}
    db: AsyncSession = Depends(get_db),
):
    """【鉴权】JSON 登录。请求体为 application/json：{"username","password"}"""
    user = await check_password(users, db)  # 内部已做 bcrypt 校验，失败抛 401
    token = create_access_token({
        "user_id": str(user.user_id),
        "role": str(user.user_role),
    })
    return {"access_token": token, "token_type": "bearer"}


@user_router.post("/token")
async def login_form(
    form: OAuth2PasswordRequestForm = Depends(),  # 表单登录：/docs 右上角 Authorize 直接可用
    db: AsyncSession = Depends(get_db),
):
    """【鉴权】标准表单登录。请求体为 x-www-form-urlencoded：username=..&password=.."""
    user_in = User(username=form.username, password=form.password)
    user = await check_password(user_in, db)  # 内部已做 bcrypt 校验，失败抛 401
    token = create_access_token({
        "user_id": str(user.user_id),
        "role": str(user.user_role),
    })
    return {"access_token": token, "token_type": "bearer"}
