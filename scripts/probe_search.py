"""Can we resolve the 定数表 cards by song title via /chart?search=?

Titles in the table are far more legible than the tiny #ids, so title->id
resolution (then name verification) is the robust path.
"""

from phira_pp.api import PhiraClient

client = PhiraClient()

QUERIES = ["MixxioN", "DISANIMATE", "Greeting into Abyss", "Vigiléa's Destiny",
           "Period.", "Dextroy", "Apollo", "CALAMITY RHAPSODY"]

for q in QUERIES:
    try:
        d = client.search_charts(search=q, pageNum=10)
    except Exception as exc:  # noqa: BLE001
        print(f"{q!r}: ERROR {type(exc).__name__}: {str(exc)[:90]}")
        continue
    rows = d.get("results") or []
    print(f"{q!r} -> {[(r['id'], r['name'][:28], r['difficulty']) for r in rows[:6]]}")

# also verify one id read from the image
for cid in (34918, 33578):
    try:
        m = client.get_chart(cid)
        print(f"#{cid} name={m.name!r} difficulty={m.difficulty} ranked={m.ranked} level={m.level}")
    except Exception as exc:  # noqa: BLE001
        print(f"#{cid} ERROR {type(exc).__name__}")
