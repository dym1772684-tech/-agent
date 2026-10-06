import redis

# 建立连接
r = redis.Redis(
    host="127.0.0.1",
    port=6379,
    decode_responses=True,  # 自动把bytes转字符串，开发必备
    password="3820023130dym",
)

# 测试读写
r.set("demo_key", "hello docker redis")
print(r.get("demo_key"))
