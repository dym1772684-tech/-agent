from pydantic import BaseModel,Field
from datetime import datetime
class HealthRecord_create(BaseModel):
    health_id:int=Field(...,description="health_id")
    elder_id:str=Field(...,max_length=64)##【修复】原 Field(...,mt=64) 中 mt 是无效参数（Pydantic 字符串长度用 max_length），会导致建模报错
    device_id:str=Field(...,max_length=64)##【修复】同上，mt=64 改为 max_length=64
    metric_type:str
    risk_content:dict=Field(default_factory=dict)##【优化】给默认空字典，请求缺该字段时不再校验失败
    value:float
    extra:dict=Field(default_factory=dict)##【优化】同上
    record_time :datetime=Field(default_factory=datetime.now)##【修复】原 Field(datetime.now()) 在模块导入时就固定一个时间，应使用 default_factory 每次生成
