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


st, b = post(f"{BASE}/login", {"username": "testuser01", "password": "test123456"})
tok = b.get("access_token")

# debug=True 也要求响应精简
st, b = post(
    f"{BASE}/agent/chat",
    {"message": "你好，介绍一下这个养生智能体能做什么", "debug": True},
    {"Authorization": f"Bearer {tok}"},
)
print("chat HTTP:", st)
d = b.get("data", {})
print("响应顶层键:", sorted(d.keys()))
print("answer 长度:", len(d.get("answer") or ""))
print("structured 键:", list((d.get("structured") or {}).keys()))
leaked = [k for k in ("query", "intent", "phase", "next_need", "tool_results", "trace") if k in d]
print("泄漏的过程字段:", leaked if leaked else "无（前端只看到最终回答）")
print("=== SLIM RESPONSE VERIFY DONE ===")
