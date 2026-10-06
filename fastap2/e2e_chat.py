import json
import urllib.request

BASE = "http://127.0.0.1:8000/api/v1"


def post(url, payload, headers=None):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=150) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


# 1. 登录拿 token
st, body = post(f"{BASE}/login", {"username": "testuser01", "password": "test123456"})
print("登录:", st)
token = body["access_token"]

# 2. 调 agent/chat（中文消息）
st, body = post(
    f"{BASE}/agent/chat",
    {"message": "你好，介绍一下这个养生智能体能做什么", "debug": True},
    {"Authorization": f"Bearer {token}"},
)
print("chat HTTP:", st)
d = body.get("data", {})
print("intent  :", d.get("intent"))
print("phase   :", d.get("phase"))
print("answer 长度:", len(d.get("answer") or ""))
print("answer 前100字:", (d.get("answer") or "")[:100])
print("query   :", json.dumps(d.get("query"), ensure_ascii=False, default=str)[:150])
print("next_need:", json.dumps(d.get("next_need"), ensure_ascii=False, default=str)[:150])
print("structured 键:", list((d.get("structured") or {}).keys()))
print("trace 步数:", len(d.get("trace") or []))
for t in d.get("trace") or []:
    print(f"  trace step{t['step']}: {t['node']} msgs={t['messages_total']} fields={list(t.get('fields', {}).keys())}")
print("=== HTTP E2E VERIFY DONE ===")
