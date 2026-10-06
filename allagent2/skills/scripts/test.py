import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def call_api_with_retry(url, params=None):
    # 配置重试策略：总共重试3次，每次间隔1秒
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    session.mount('https://', HTTPAdapter(max_retries=retries))

    # 动态生成签名
    import hmac, hashlib, base64, time, random, string
    timestamp = str(int(time.time() * 1000))
    nonce = "".join(random.choices(string.ascii_letters + string.digits, k=16))
    raw = f"{CLIENT_ID}{timestamp}{nonce}"
    signature = base64.b64encode(hmac.new(CLIENT_SECRET.encode(), raw.encode(), hashlib.sha256).digest()).decode()

    headers = {
        "X-Client-Id": CLIENT_ID,
        "X-Timestamp": timestamp,
        "X-Nonce": nonce,
        "X-Signature": signature,
    }

    # 增加 timeout，并强制使用 https
    url = url.replace("http://", "https://")
    
    try:
        resp = session.get(url, headers=headers, params=params, timeout=60)
        return resp.json()
    except requests.exceptions.ReadTimeout:
        print("⚠️ 请求超时，建议检查网络或稍后再试。")
        return None
    except Exception as e:
        print(f"⚠️ 请求出错: {e}")
        return None