from fastapi.security import OAuth2PasswordBearer
from schemas.user import User
oauth2_schema=OAuth2PasswordBearer(tokenUrl="token")
"""
1. 护工登录后台 → POST `/token`，账号密码校验，生成 JWT 返回
2. 护工调用接口：查询老人档案、查看健康风险记录
3. 请求头带上 Bearer token
4. `OAuth2PasswordBearer` 提取 token 字符串
5. `jwt.decode` 校验签名 + 判断是否过期，取出 user_id、角色
6. 代码判断：该护工是否有权限访问这个老人的数据
7. token 过期 → 前端提示重新登录"""
from typing import Annotated
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from fastapi import APIRouter
from sqlalchemy.orm import Session
from sqlalchemy import select
from database.database import get_db
from passlib.context import CryptContext
from models.users import User_table
from datetime import datetime,timedelta,timezone##【优化】引入 timezone：JWT 的 exp 按规范应使用 UTC 时间
import jwt
import os
import bcrypt
from dotenv import find_dotenv, load_dotenv
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / "core" / "key.env"
load_dotenv(find_dotenv(str(ENV_PATH)))

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
if not SECRET_KEY:
    raise RuntimeError("JWT SECRET_KEY missing. Please confirm fastap2/core/key.env exists and contains SECRET_KEY.")

oauth2_schema = OAuth2PasswordBearer(tokenUrl="/api/v1/token")  # 【鉴权】表单登录端点（/docs Authorize 使用）


def _normalize_bcrypt_password(password: str | bytes) -> bytes:
    """bcrypt 只接受最多 72 bytes 的密码；按 UTF-8 字节长度截断。"""
    if isinstance(password, str):
        raw = password.encode("utf-8")
    else:
        raw = bytes(password)
    return raw[:72]


def hash_password(users: User):
    thing = _normalize_bcrypt_password(users.password)
    return bcrypt.hashpw(thing, bcrypt.gensalt(rounds=12)).decode("utf-8")


def decode_jwt(token):
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    return payload


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=30))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def check_password(users: User, db: AsyncSession):
    result = await db.execute(
        select(User_table)
        .where(User_table.username == users.username)
        .order_by(User_table.id.asc())
    )
    end_result = result.scalars().first()
    if end_result is None:
        raise HTTPException(status_code=401, detail="账号或密码错误")

    user_input = _normalize_bcrypt_password(users.password)
    try:
        is_ok = bcrypt.checkpw(user_input, end_result.password.encode("utf-8"))
    except ValueError:
        raise HTTPException(status_code=401, detail="账号或密码错误")
    if not is_ok:
        raise HTTPException(status_code=401, detail="账号或密码错误")
    return end_result


async def check_jwt(token: str = Depends(oauth2_schema), db: AsyncSession = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token 无效或已过期")

    user_id = payload.get("user_id")
    role = payload.get("role")
    if not user_id or not role:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token 缺少用户信息")

    result = await db.execute(select(User_table).where(User_table.user_id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    if user.user_role != role:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="角色不匹配")
    return user
    #########差一个客户端报文jwt解析内容

# ============================================================
# 【鉴权】新增：当前登录用户依赖 + RBAC 角色控制依赖
# ============================================================

# 任意受保护接口把参数写成 current: CurrentUser，
# FastAPI 就会自动执行 check_jwt（验签+查库）并注入当前登录用户对象。
CurrentUser = Annotated[User_table, Depends(check_jwt)]


def require_roles(*allowed_roles: str):
    """【鉴权】RBAC 角色控制依赖工厂。

    用法（挂到单个接口或整个 router）：
        Depends(require_roles("admin"))
        Depends(require_roles("nurse", "admin"))

    流程：先经 check_jwt 确认已登录（否则 401），再校验角色；
    角色不在允许名单内 → 403 权限不足。
    """
    async def checker(current: User_table = Depends(check_jwt)):
        if current.user_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足",
            )
        return current

    return checker
