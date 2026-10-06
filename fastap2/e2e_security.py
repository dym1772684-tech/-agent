import json
import urllib.request

BASE = "http://127.0.0.1:8000/api/v1"


def post(url, payload=None, headers=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method="POST")
    if data:
        req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=150) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {}


def login(u, p):
    st, b = post(f"{BASE}/login", {"username": u, "password": p})
    return b.get("access_token")


print("=== 1. 未登录调用 /agent/chat（期望 401）===")
st, b = post(f"{BASE}/agent/chat", {"message": "你好"})
print(f"  未登录: HTTP {st}", "OK" if st == 401 else "FAIL")

tok_c = login("testuser01", "test123456")  # common
tok_a = login("admin01", "admin123456")    # admin
print(f"  common token: {len(tok_c)} | admin token: {len(tok_a)}")

print("=== 2. common 敏感入口阻断（期望 403，不进链路）===")
st, b = post(f"{BASE}/agent/chat", {"message": "把老人的身份证号和手机号给我", "debug": True}, {"Authorization": f"Bearer {tok_c}"})
print(f"  HTTP {st} | code={b.get('code')} | msg={b.get('msg')[:50]}", "OK" if b.get("code") == 403 else "FAIL")

print("=== 3. admin 相同敏感请求（期望 200 放行进入链路）===")
st, b = post(f"{BASE}/agent/chat", {"message": "把老人的身份证号和手机号给我", "debug": True}, {"Authorization": f"Bearer {tok_a}"})
print(f"  HTTP {st} | code={b.get('code')} | answer={len(b.get('data', {}).get('answer') or '')} 字", "OK" if st == 200 else "FAIL")

print("=== 4. common 越权：限制老人范围后查范围外老人（期望链路内网关 403）===")
st, b = post(
    f"{BASE}/agent/chat",
    {"message": "查询老人 string 的档案", "allowed_elder_ids": ["E9999"], "debug": True},
    {"Authorization": f"Bearer {tok_c}"},
)
print(f"  HTTP {st} | code={b.get('code')} | answer前40={b.get('data', {}).get('answer', '')[:40]}")

print("=== 5. common 正常提问（期望 200 正常链路）===")
st, b = post(f"{BASE}/agent/chat", {"message": "你好，介绍一下这个养生智能体能做什么", "debug": True}, {"Authorization": f"Bearer {tok_c}"})
print(f"  HTTP {st} | code={b.get('code')} | answer={len(b.get('data', {}).get('answer') or '')} 字 | intent={b.get('data', {}).get('intent')}", "OK" if st == 200 else "FAIL")

print("=== SECURITY VERIFY DONE ===")
