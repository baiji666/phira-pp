"""Path discovery with a valid token: is there a direct 'my records' endpoint?"""

import requests

from phira_pp.api import load_token

S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0"
tok = load_token()
if tok:
    S.headers["Authorization"] = f"Bearer {tok}"
print("token present:", bool(tok))

HOST = "https://phira.5wyxi.com"
U, C = 0, 16593

PATHS = [
    f"/record/best/{C}",
    f"/record/best_std/{C}",
    f"/record/std/{C}",
    "/record/me",
    "/record/self",
    "/record/list",
    "/record/all",
    "/record/recent",
    "/record/query",
    f"/user/{U}/records",
    f"/user/{U}/record",
    f"/user/{U}/best",
    f"/user/{U}/pool",
    f"/record/get-pool/{U}",
    f"/record/best/{C}?full=1",
    f"/record/best/{C}?std=1",
]

for p in PATHS:
    try:
        r = S.get(HOST + p, timeout=30)
    except Exception as exc:  # noqa: BLE001
        print(f"{p:38s} ERR {type(exc).__name__}")
        continue
    flag = "  <<< 200" if r.status_code == 200 else ""
    print(f"{p:38s} {r.status_code} {r.text[:130].replace(chr(10), ' ')}{flag}")
