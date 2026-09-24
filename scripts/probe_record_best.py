"""Reveal the shape of ``/record/best/{user}`` (SuonasiOS's own score endpoint).

Needs a Phira auth token:  export PHIRA_TOKEN=...   (never printed here)
Without a token it demonstrates the 401 that forces anonymous clients to scan.
"""

import json
import os

import requests

from phira_pp.api import TOKEN_FILE, TOKEN_ENV, load_token

TOKEN = load_token()
USER = int(os.environ.get("USER_ID", "0"))

S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0"
if TOKEN:
    S.headers["Authorization"] = f"Bearer {TOKEN}"
print(f"token present: {bool(TOKEN)}  (source: ${TOKEN_ENV} or {TOKEN_FILE}; never printed)")

for host in ("https://phira.5wyxi.com", "https://api.phira.cn"):
    for path in (f"/record/best/{USER}", f"/record/best/{USER}?page=1&pageNum=100"):
        try:
            r = S.get(host + path, timeout=40)
        except Exception as exc:  # noqa: BLE001
            print(f"{host}{path} -> ERR {type(exc).__name__}")
            continue
        print(f"\n### {host}{path} -> {r.status_code} len={len(r.content)}")
        print("   body:", r.text[:200].replace("\n", " "))
        if r.status_code == 200:
            try:
                data = r.json()
            except Exception:  # noqa: BLE001
                continue
            if isinstance(data, dict):
                print("   dict keys:", list(data.keys())[:20])
                for k, v in data.items():
                    if isinstance(v, list):
                        print(f"   {k}: list[{len(v)}] first={json.dumps(v[0], ensure_ascii=False)[:300] if v else None}")
                    else:
                        print(f"   {k}: {str(v)[:120]}")
            elif isinstance(data, list):
                print(f"   list[{len(data)}] first={json.dumps(data[0], ensure_ascii=False)[:400] if data else None}")
