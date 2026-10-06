from pydantic import BaseModel
from typing import Optional
class User(BaseModel):
    username:str
    password:str
    # 【优化】注册接口只需要 username/password；原 email/full_nmae/disabled/role/user_id
    # 全部必填，会导致正常注册请求因缺字段直接 422。改为可选并给默认值。
    email:Optional[str]=None
    full_nmae:Optional[str]=None
    disabled:bool=False##注册时默认未禁用
    role:str="common"
    user_id:Optional[str]=None
