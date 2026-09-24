"""What does /record/best/{chart} actually mean?

Check a few charts: compare its score against the chart's #1 and whether the
token owner really appears in that chart's records.
"""

import json

import requests

from phira_pp.api import load_token

S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0"
tok = load_token()
if tok:
    S.headers["Authorization"] = f"Bearer {tok}"

H = "https://phira.5wyxi.com"
U = 0

ids = [r["id"] for r in json.load(open("data/kv_diff.json", encoding="utf-8"))["rows"]]
picks = [ids[0], ids[1], ids[3], ids[len(ids) // 2], ids[-1], 16593]

for cid in picks:
    b = S.get(f"{H}/record/best/{cid}", timeout=30)
    q = S.get(f"{H}/record/query/{cid}?page=1&pageNum=30", timeout=30).json()
    rows = q.get("results") or []
    me = [r for r in rows if r["player"] == U]
    top1 = rows[0]["score"] if rows else None
    best = b.text[:70]
    print(f"#{cid:<7d} best={best:<72s}")
    print(f"          count={q.get('count')} top1_score={top1} me_in_top30={bool(me)}")
