"""Size up the full catalogue: totals, division values, ranked filter, paging."""

from phira_pp.api import PhiraClient

c = PhiraClient()


def count(**kw):
    try:
        d = c.search_charts(page=1, pageNum=1, **kw)
        return d.get("count"), len(d.get("results") or [])
    except Exception as exc:  # noqa: BLE001
        return f"ERR {type(exc).__name__}: {str(exc)[:60]}", None


print("total (no filter):", count())
for div in ("regular", "troll", "visual", "plain", "special", "config", "story",
            "SP", "specialstory", "tutorial", "local"):
    print(f"  division={div:14s} ->", count(division=div)[0])

print("\nranked filters:")
for kw in ({"ranked": True}, {"ranked": "true"}, {"ranked": 1}):
    print(f"  {kw} ->", count(**kw)[0])

print("\nregular + ranked:", count(division="regular", ranked=True)[0])
print("regular count again:", count(division="regular")[0])

print("\npageNum limit (regular):")
for pn in (30, 100, 1000):
    n, rows = count(division="regular", pageNum=pn)
    print(f"  pageNum={pn:<5d} count={n} rows_returned={rows}")

print("\norder options (regular):")
for order in (None, "rating", "-rating", "name", "-name", "-updated", "-created", "difficulty", "-difficulty"):
    n, rows = count(division="regular", **({"order": order} if order else {}))
    print(f"  order={str(order):12s} -> count={n} rows={rows}")
