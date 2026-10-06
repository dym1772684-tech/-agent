"""诊断：前端 payload 哪些会触发 /agent/chat 422"""
import json
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8000/api/v1"


def post(url, payload, headers=None):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {}


# 登录拿 token
st, b = post(f"{BASE}/login", {"username": "testuser01", "password": "test123456"})
tok = b.get("access_token")
H = {"Authorization": f"Bearer {tok}"}

cases = [
    ("正常问题", {"message": "你好", "debug": True}),
    ("空message", {"message": "", "debug": True}),
    ("缺message", {"debug": True}),
    ("空elder_id+空thread_id(前端undefined被丢弃)", {"message": "你好", "debug": True}),
    ("message为null", {"message": None, "debug": True}),
    ("debug字符串", {"message": "你好", "debug": "true"}),
    ("elder_id数字", {"message": "你好", "elder_id": 123, "debug": True}),
]
for name, payload in cases:
    st2, b2 = post(f"{BASE}/agent/chat", payload, H)
    d = b2.get("detail") if isinstance(b2, dict) else None
    print(f"[{name}] status={st2} detail={json.dumps(d, ensure_ascii=False)[:200] if d else b2}")
