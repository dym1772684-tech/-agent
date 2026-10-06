from sqlalchemy import Column, String, Text, DateTime, Integer
from sqlalchemy.orm import Session
from sqlalchemy import UniqueConstraint
from database.database import Base
import datetime
class User_table(Base):
    __tablename__="User"
    id=Column(Integer,primary_key=True,autoincrement=True)
    username=Column(String(64), unique=True, nullable=False)
    password=Column(String(64), nullable=False)
    create_time=Column(DateTime,default=datetime.datetime.now)
    user_id=Column(String(64), unique=True, nullable=False)
    user_role=Column(String(64), default="common")

    __table_args__ = (
        UniqueConstraint('username', name='uq_user_username'),
        UniqueConstraint('user_id', name='uq_user_user_id'),
    )
