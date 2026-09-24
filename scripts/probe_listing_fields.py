"""What does the /chart listing actually return, and does `division` filter work?"""

import json

from phira_pp.api import PhiraClient

client = PhiraClient()

data = client.search_charts(page=1, pageNum=3, order="rating")
rows = data.get("results") or data.get("result") or []
print("top-level keys:", list(data.keys()))
print("row keys:", list(rows[0].keys()))
print("sample row:", json.dumps(rows[0], ensure_ascii=False)[:400])

ids = lambda p: [r["id"] for r in (p.get("results") or [])]
base = client.search_charts(page=1, pageNum=5, order="rating")
for div in ("regular", "troll", "visual", "plain"):
    try:
        d = client.search_charts(page=1, pageNum=5, order="rating", division=div)
        r = d.get("results") or []
        print(f"division={div:8s} rows={len(r)} count={d.get('count')} "
              f"diff_sample={[x.get('difficulty') for x in r[:5]]} "
              f"same_ids_as_unfiltered={ids(d) == ids(base)[:len(ids(d))]}")
    except Exception as exc:  # noqa: BLE001
        print(f"division={div:8s} ERROR {type(exc).__name__}: {str(exc)[:90]}")
