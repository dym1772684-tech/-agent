
from pydantic import BaseModel
from typing import Any, Optional


class ApiResponse(BaseModel):
    code: int
    msg: str
    data: Optional[Any] = None

    @classmethod
    def success(cls, data: Any = None, msg: str = "success"):
        return cls(code=200, msg=msg, data=data)

    @classmethod
    def fail(cls, code: int, msg: str, data: Any = None):
        return cls(code=code, msg=msg, data=data)
