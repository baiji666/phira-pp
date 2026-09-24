"""Verify /chart pagination AND which `order` values are valid (errors shown)."""

from phira_pp.api import PhiraClient
from phira_pp.dataset import Dataset

client = PhiraClient()


def probe(order=None, pages=5, page_num=30):
    label = order if order is not None else "<none>"
    print(f"order={label!r}")
    prev = None
    seen = set()
    for page in range(1, pages + 1):
        try:
            data = client.search_charts(page=page, pageNum=page_num,
                                        **({"order": order} if order else {}))
        except Exception as exc:  # noqa: BLE001 - report, never swallow
            print(f"  page {page}: ERROR {type(exc).__name__}: {str(exc)[:120]}")
            break
        rows = data.get("results") or data.get("result") or []
        ids = [r["id"] for r in rows]
        overlap = len(set(ids) & prev) if prev is not None else 0
        seen |= set(ids)
        print(f"  page {page}: rows={len(ids)} overlap_with_prev={overlap} "
              f"cum_unique={len(seen)} first3={ids[:3]}")
        prev = set(ids)
    print(f"  => valid={prev is not None} unique={len(seen)}")


for o in ("rating", "-rating", "update", "-update", "name", None):
    probe(order=o)

print("\nDataset.iter_ranked_metas dedup check (limit 120):")
ds = Dataset()
ids = [m.id for m in ds.iter_ranked_metas(120)]
print(f"  yielded={len(ids)} unique={len(set(ids))} duplicates={len(ids) - len(set(ids))}")
