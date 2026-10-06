import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / "database" / "mysql.env"
load_dotenv(find_dotenv(str(ENV_PATH)))

MYSQL_USER = os.getenv("MYSQL_USER")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = os.getenv("MYSQL_PORT", "3306")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE")

if not all([MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE]):
    raise RuntimeError(
        "MySQL env missing. Please confirm fastap2/database/mysql.env contains MYSQL_USER/MYSQL_PASSWORD/MYSQL_DATABASE."
    )

db_url = (
    f"mysql+aiomysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"
)
engine = create_async_engine(
    db_url,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=3600,
)
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    db = AsyncSessionLocal()
    try:
        yield db
    finally:
        await db.close()



# 兼容旧代码：有些模块使用 `from database.database import AsyncSession, Session`
# 因此需要在模块顶层显式导出这些名字。
__all__ = ["Base", "Session", "AsyncSession", "engine", "AsyncSessionLocal", "get_db"]

# class AgentConversation(Base):#创建表
#     __tablename__ = "agent_conversation"##表名

#     id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
#     session_id: Mapped[str]
#     user_query: Mapped[str] = mapped_column(Text)
#     llm_response: Mapped[Optional[str]] = mapped_column(Text)
#     tool_calls: Mapped[Optional[str]] = mapped_column(Text)
#     create_time: Mapped[DateTime] = mapped_column(DateTime, default=func.CURRENT_TIMESTAMP)
#     update_time: Mapped[DateTime] = mapped_column(DateTime, default=func.CURRENT_TIMESTAMP, onupdate=func.CURRENT_TIMESTAMP)
# class User(Base):
#     __tablename__ = "users"  # 指定数据库中的表名

#     # Mapped[int] 是 Python 类型提示，告诉 IDE 这个字段是 int
#     # mapped_column(...) 才是真正的数据库列定义
#     id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
#     username: Mapped[str] = mapped_column(nullable=False, length=50)  # NOT NULL
#     email: Mapped[Optional[str]] = mapped_column(length=100)          # Optional 表
# Base.metadata.create_all(bind=engine)
# print("✅ 表结构创建/检查完成")
# with SessionLocal() as session:
#     user=User(username="alice",email="alice@test.com")
#     session.add(user)
#     session.commit()  # 提交后才真正写入数据库
#     print(f"✅ 插入单条成功，用户ID: {user.id}")
#     users_to_add = [
#         User(username="bob", email="bob@test.com"),
#         User(username="charlie", email="charlie@test.com"),
#         User(username="diana", email="diana@test.com")
#     ]
#     session.add_all(users_to_add)
#     session.commit()
#     print(f"✅ 批量插入成功，共插入 {len(users_to_add)} 条")
# with SessionLocal() as session:
#     stmt=select(User)
#     all_users=session.execute(stmt).scalars().all()
#     for u in len(all_users):
#         print(f"   ID: {u.id}, Name: {u.username}, Email: {u.email}")
#     stmt=select(User).where(User.username=="alice")
#     alice=session.execute(stmt).scalar_one_or_none()
#     if alice:
#         print(f"\n🔍 查询到 alice: ID={alice.id}, Email={alice.email}")
#     else:
#         print("\n❌ 未找到 alice")
# # 2.3 模糊查询
#     stmt = select(User).where(User.email.like("%test.com"))
#     test_users = session.execute(stmt).scalars().all()
#     print(f"\n🔍 邮箱包含 'test.com' 的用户 ({len(test_users)} 条):")
#     for u in test_users:
#         print(f"   {u.username} -> {u.email}")
    
#     # 2.4 查询第一条
#     stmt = select(User).limit(1)
#     first_user = session.execute(stmt).scalar_one()
#     print(f"\n📌 第一个用户: {first_user.username}")
    
#     # 2.5 查询并排序
#     stmt = select(User).order_by(User.id.desc())  # 按 ID 降序
#     recent_users = session.execute(stmt).scalars().all()
#     print(f"\n📌 按 ID 降序排列（最新在前）:")
#     for u in recent_users[:3]:  # 只显示前3条
#         print(f"   ID: {u.id}, Name: {u.username}")

# # ========================================

# # 3. 修改（Update）—— 更新数据
# with SessionLocal() as session:
#     print("\n========== 3. 修改数据 ==========")
    
#     # 3.1 先查出来再改（推荐方式）
#     stmt = select(User).where(User.username == "bob")
#     bob = session.execute(stmt).scalar_one_or_none()
    
#     if bob:
#         print(f"修改前: {bob.username} -> {bob.email}")
#         bob.email = "bob_new@test.com"  # 改内存中的值
#         session.commit()  # 提交后自动生成 UPDATE 语句
#         print(f"修改后: {bob.username} -> {bob.email}")
#     else:
#         print("❌ 未找到 bob")
    
#     # 3.2 批量更新（使用 update 语句，更高效）
#     from sqlalchemy import update
#     stmt = update(User).where(User.username == "charlie").values(email="charlie_updated@test.com")
#     result = session.execute(stmt)
#     session.commit()
#     print(f"✅ 批量更新影响行数: {result.rowcount}")

# # ========================================

# # 4. 删除（Delete）—— 删除数据
# with SessionLocal() as session:
#     print("\n========== 4. 删除数据 ==========")
    
#     # 4.1 先查出来再删（推荐方式）
#     stmt = select(User).where(User.username == "diana")
#     diana = session.execute(stmt).scalar_one_or_none()
    
#     if diana:
#         session.delete(diana)  # 标记删除
#         session.commit()  # 真正执行 DELETE
#         print(f"✅ 已删除用户: {diana.username}")
#     else:
#         print("❌ 未找到 diana")
    
#     # 4.2 批量删除（使用 delete 语句）
#     from sqlalchemy import delete
#     stmt = delete(User).where(User.username == "charlie")
#     result = session.execute(stmt)
#     session.commit()
#     print(f"✅ 批量删除影响行数: {result.rowcount}")

# # ========================================

# # 5. 高级查询技巧（补充）
# with SessionLocal() as session:
#     print("\n========== 5. 高级查询 ==========")
    
#     # 5.1 统计总数
#     from sqlalchemy import func
#     stmt = select(func.count()).select_from(User)
#     count = session.execute(stmt).scalar()  # scalar() 取单个值
#     print(f"📊 用户表总记录数: {count}")
    
#     # 5.2 检查用户是否存在
#     stmt = select(User).where(User.username == "alice")
#     exists = session.execute(stmt).first() is not None
#     print(f"🔍 alice 是否存在? {'是' if exists else '否'}")
    
#     # 5.3 只查询特定字段（返回元组，不是对象）
#     stmt = select(User.username, User.email)  # 注意：这里没有 .where
#     rows = session.execute(stmt).all()
#     print("\n📌 只查询 username 和 email:")
#     for username, email in rows:
#         print(f"   {username} -> {email}")

# # ========================================

# print("\n🎉 所有操作执行完毕！")       
#     # 退出 with 时自动 close
# # with engine.begin() as conn:
# #     conn.execute(text("""
# #     create table if not exists users(
# #     id int primary key auto_increment,
# #     username varchar(50) not NULL,
# #     email varchar(100)
# #     )
    
    
# #     """)
# #     )
# #     conn.execute(text(
# #         "insert into users (username,email) values(:username,:email)"
# #     ),
# #         [
# #             {"username":"alice","email":"alice@test.com"},
# #             {"username":"bob","email":"bob@test.com"}
            
# #         ])