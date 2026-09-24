"""With a valid token: work out what /record/best/{...} actually takes.

401 -> 404 means auth passed and the route matched but the entity didn't, which
suggests the trailing number is a *chart* id rather than a user id.  Test both.
"""

import json

import requests

from phira_pp.api import load_token

TOKEN = load_token()
S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0"
if TOKEN:
    S.headers["Authorization"] = f"Bearer {TOKEN}"
print("token present:", bool(TOKEN))

HOST = "https://phira.5wyxi.com"
USER, CHART = 0, 16593

CANDIDATES = [
    f"/record/best/{CHART}",
    f"/record/best/{CHART}?player={USER}",
    f"/record/best/{CHART}?user={USER}",
    f"/record/best/{USER}",
    f"/record/best/{USER}?chart={CHART}",
    f"/user/{USER}",
    f"/record/query/{CHART}",
]

for path in CANDIDATES:
    try:
        r = S.get(HOST + path, timeout=40)
    except Exception as exc:  # noqa: BLE001
        print(f"{path:46s} ERR {type(exc).__name__}")
        continue
    print(f"\n### {path}  -> {r.status_code} len={len(r.content)}")
    body = r.text[:220].replace("\n", " ")
    print("    ", body)
    if r.status_code == 200:
        try:
            d = r.json()
        except Exception:  # noqa: BLE001
            continue
        if isinstance(d, dict):
            print("     keys:", list(d.keys())[:14])
            for k, v in d.items():
                if isinstance(v, list) and v:
                    print(f"     {k}: list[{len(v)}] first={json.dumps(v[0], ensure_ascii=False)[:320]}")
        elif isinstance(d, list) and d:
            print(f"     list[{len(d)}] first={json.dumps(d[0], ensure_ascii=False)[:320]}")
