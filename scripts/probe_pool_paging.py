"""Two things that decide the fast design:
  1. is /record/get-pool paged (i.e. can we get more than the rks pool)?
  2. is /record/query sorted by score descending (so a known score can locate a
     player's record by page math instead of scanning)?
"""

import requests

from phira_pp.api import load_token

S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0"
tok = load_token()
if tok:
    S.headers["Authorization"] = f"Bearer {tok}"

HOST = "https://phira.5wyxi.com"
U, C = 459003, 16593

print("=== get-pool length / paging ===")
for q in ("", "?page=1&pageNum=100", "?page=2&pageNum=100", "?pageNum=1000"):
    r = S.get(f"{HOST}/record/get-pool/{U}{q}", timeout=30)
    if r.status_code != 200:
        print(f"  {q:22s} {r.status_code} {r.text[:90]}")
        continue
    d = r.json()
    pool = d.get("bestPool") or []
    print(f"  {q:22s} keys={list(d.keys())[:6]} bestPool_len={len(pool)}")
    if pool:
        print(f"      first={pool[0]}")

print("\n=== /record/query score ordering (page 1..3, pageNum=30) ===")
prev = None
for page in (1, 2, 3):
    d = S.get(f"{HOST}/record/query/{C}?page={page}&pageNum=30", timeout=30).json()
    scores = [x["score"] for x in d["results"]]
    ok = all(scores[i] >= scores[i + 1] for i in range(len(scores) - 1))
    cont = "" if prev is None else f" | crosses_prev={prev >= scores[0]}"
    print(f"  page {page}: n={len(scores)} max={max(scores)} min={min(scores)} "
          f"descending={ok}{cont}")
    prev = min(scores)

print("\n=== can a known record id be fetched directly? ===")
d = S.get(f"{HOST}/record/query/{C}?page=1&pageNum=2", timeout=30).json()
rid = d["results"][0]["id"]
r = S.get(f"{HOST}/record/{rid}", timeout=30)
print(f"  /record/{rid} -> {r.status_code} {r.text[:220]}")
