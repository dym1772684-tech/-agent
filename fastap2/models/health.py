
from database.database import Base
# 【优化】datetime.utcnow() 在 Python 3.12 起被弃用（naive UTC 易出错）。
# 改为显式取 timezone-aware 的 UTC 时间，再去掉 tzinfo 以匹配 MySQL 的 DateTime（naive）；
# 写入的时间数值仍是 UTC，与原 utcnow() 完全一致，只是消除了弃用告警、语义更明确。
from datetime import datetime, timezone
from sqlalchemy import Column,String,Float,DateTime,Integer,JSON

def _utcnow():
    # 统一的 UTC 默认时间工厂（替代两处 datetime.datetime.utcnow）
    return datetime.now(timezone.utc).replace(tzinfo=None)

class HealthRecord(Base):
    __tablename__ = "health_record"
    id = Column(Integer, primary_key=True, autoincrement=True)
    elder_id = Column(String(64), index=True) # 建议给String加上长度，mysql最佳实践
    device_id = Column(String(64), nullable=True)
    metric_type = Column(String(32), index=True)
    value = Column(Float)
    risk_content=Column(JSON)
    extra = Column(JSON, nullable=True)
    record_time = Column(DateTime, index=True)
    create_time = Column(DateTime, default=_utcnow)##【优化】default 改用 _utcnow（原 datetime.datetime.utcnow）

class HealthRisk(Base):
    __tablename__ = "health_risk"
    id = Column(Integer, primary_key=True, autoincrement=True)
    elder_id = Column(String(64), index=True)
    risk_level = Column(String(32))
    risk_content = Column(JSON)
    create_time = Column(DateTime, default=_utcnow)##【优化】default 改用 _utcnow（原 datetime.datetime.utcnow）
