"""Scan the chart catalogue (metadata only) to size a stratified training sample.

Uses only order values verified to work ("rating", "-rating", "name", and the
default newest-first); "update"/"-update" are rejected by the API with 400.
Errors are reported, never swallowed.
"""

import collections
import sys

from phira_pp.api import PhiraClient, _meta_from_dict

ORDERS = ("-rating", "rating", "name", None)


def main(pages: int = 60, page_num: int = 30):
    client = PhiraClient()
    seen: dict[int, float] = {}          # ranked + reviewed
    all_seen: dict[int, float] = {}      # every chart returned
    div = collections.Counter()
    errors = 0
    total_count = None

    for order in ORDERS:
        label = order if order else "<newest>"
        got = 0
        for page in range(1, pages + 1):
            try:
                data = client.search_charts(page=page, pageNum=page_num,
                                            **({"order": order} if order else {}))
            except Exception as exc:  # noqa: BLE001 - report explicitly
                print(f"  ! order={label} page={page} ERROR {type(exc).__name__}: {str(exc)[:90]}")
                errors += 1
                break
            if total_count is None:
                total_count = data.get("count")
            rows = data.get("results") or data.get("result") or []
            if not rows:
                break
            got += len(rows)
            for row in rows:
                meta = _meta_from_dict(row)
                all_seen.setdefault(meta.id, meta.difficulty)
                if not (meta.ranked and meta.reviewed):
                    continue
                div[meta.division] += 1
                seen.setdefault(meta.id, meta.difficulty)
        print(f"  order={label:9s} rows_scanned={got} unique_total={len(all_seen)}")

    print(f"\ncatalogue count field: {total_count}")
    print(f"unique charts seen: {len(all_seen)}   ranked+reviewed: {len(seen)}  (errors {errors})")
    print("division(ranked):", dict(div))

    def hist(diffs, title):
        h = collections.Counter(int(d) for d in diffs)
        print(f"\n{title} 定数 histogram:")
        for k in sorted(h):
            print(f"  {k:>3d}: {h[k]:>5d} {'#' * min(50, h[k] // 3)}")

    hist(all_seen.values(), "ALL charts")
    hist(seen.values(), "ranked+reviewed")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 60)
