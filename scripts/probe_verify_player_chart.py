"""Verify /record?player={u}&chart={c} contains the player's BEST record.

For many charts, compare max(score) among the returned rows (and the row flagged
best=true) against the authoritative /record/best/{chart} score.
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
picks = ids[:6] + ids[len(ids) // 3: len(ids) // 3 + 4] + ids[-6:] + [44231, 13, 16593, 42891, 76959, 77421]

mismatch = 0
with_std = 0
tested = 0
for cid in picks:
    rows = S.get(f"{H}/record?player={U}&chart={cid}", timeout=30).json()
    if not isinstance(rows, list):
        print(f"#{cid}: {rows}")
        continue
    b = S.get(f"{H}/record/best/{cid}", timeout=30).json()
    best_score = float(b.get("score") or 0)
    if not rows:
        print(f"#{cid:<7d} rows=0  best_score={best_score:.0f}  {'OK(not played)' if best_score == 0 else 'MISMATCH! played but rows=0'}")
        if best_score != 0:
            mismatch += 1
        continue
    tested += 1
    mx = max(float(r.get("score") or 0) for r in rows)
    flag = [r for r in rows if r.get("best")]
    flag_score = float(flag[0]["score"]) if flag else None
    stds = [r.get("std") for r in rows if r.get("std")]
    if stds:
        with_std += 1
    ok = abs(mx - best_score) < 0.5
    if not ok:
        mismatch += 1
    print(f"#{cid:<7d} rows={len(rows):<3d} max={mx:.0f} best_score={best_score:.0f} "
          f"flag={flag_score if flag_score is None else round(flag_score)} "
          f"std_rows={len(stds)} {'OK' if ok else 'MISMATCH'}")

print(f"\ntested={tested} with_std={with_std} mismatches={mismatch}")
