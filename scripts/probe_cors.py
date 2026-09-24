"""Check whether the Phira API sends CORS headers (browser-callable?)."""

import requests

for url in ("https://api.phira.cn/chart/51", "https://api.phira.cn/user/0"):
    r = requests.get(url, headers={"Origin": "http://localhost:8000"}, timeout=30)
    acao = r.headers.get("Access-Control-Allow-Origin")
    print(f"{url}\n  status={r.status_code} ACAO={acao!r} "
          f"ACAC={r.headers.get('Access-Control-Allow-Credentials')!r}")
