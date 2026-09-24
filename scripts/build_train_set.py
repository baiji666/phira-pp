"""Build a difficulty-stratified training set from the whole catalogue.

The ranked pool is narrow (定数 13-17), so we sample the general regular pool
across bands.  Quotas over-weight the thin low/high ends so the fitted model can
learn the full scale instead of shrinking towards the middle.

    python scripts/build_train_set.py --plan-only
    python scripts/build_train_set.py
"""

import argparse
import collections
import json
from pathlib import Path

from phira_pp.api import PhiraClient, _meta_from_dict
from phira_pp.dataset import Dataset

# (lo, hi, quota)  -- hi exclusive
BANDS = [
    (1, 8, 10),
    (8, 10, 15),
    (10, 12, 25),
    (12, 13, 20),
    (13, 14, 20),
    (14, 15, 15),
    (15, 16, 10),
    (16, 17, 15),
    (17, 18, 25),
    (18, 20.01, 20),
]
ORDERS = ("-rating", "rating", "name", None)
MIN_RATING_COUNT = 5
OUT = Path("data/train_ids.json")


def band_of(d):
    for lo, hi, _ in BANDS:
        if lo <= d < hi:
            return (lo, hi)
    return None


def plan(client, max_pages):
    quota = {(lo, hi): q for lo, hi, q in BANDS}
    picked: dict[tuple[int, int], list] = {k: [] for k in quota}
    seen: set[int] = set()
    requests = 0
    for order in ORDERS:
        for page in range(1, max_pages + 1):
            if all(len(v) >= quota[k] for k, v in picked.items()):
                break
            try:
                data = client.search_charts(page=page, pageNum=30, division="regular",
                                            **({"order": order} if order else {}))
            except Exception as exc:  # noqa: BLE001 - surface, never hide
                print(f"  ! listing error order={order} page={page}: {type(exc).__name__}")
                break
            requests += 1
            rows = data.get("results") or data.get("result") or []
            if not rows:
                break
            for row in rows:
                meta = _meta_from_dict(row)
                if meta.id in seen:
                    continue
                seen.add(meta.id)
                if meta.rating_count < MIN_RATING_COUNT:
                    continue
                key = band_of(meta.difficulty)
                if key is None:
                    continue
                if len(picked[key]) < quota[key]:
                    picked[key].append(meta)
        if all(len(v) >= quota[k] for k, v in picked.items()):
            break
    return picked, seen, requests


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan-only", action="store_true")
    ap.add_argument("--max-pages", type=int, default=120)
    args = ap.parse_args()

    client = PhiraClient()
    ds = Dataset(client=client)
    picked, seen, requests = plan(client, args.max_pages)

    metas = [m for v in picked.values() for m in v]
    print(f"scanned {len(seen)} unique charts ({requests} listing requests)")
    print(f"selected {len(metas)} charts for training")
    print(f"{'band':>12}  {'sel':>4} {'cached':>7} {'todo':>5}")
    todo = []
    for lo, hi, quota_ in BANDS:
        v = picked[(lo, hi)]
        cached = sum(1 for m in v if ds.features_path(m.id).exists())
        print(f"{lo:>5}-{hi:<6}  {len(v):>4} {cached:>7} {len(v)-cached:>5}")
        todo += [m for m in v if not ds.features_path(m.id).exists()]

    if args.plan_only:
        print(f"\nplan-only: would download {len(todo)} new packages")
        return

    print(f"\ndownloading/parsing {len(todo)} new charts ...")
    ok = fail = 0
    for i, meta in enumerate(todo, 1):
        feats = None
        try:
            feats = ds.get_features(meta)
        except Exception as exc:  # noqa: BLE001 - surface failures
            print(f"  ! #{meta.id} failed: {type(exc).__name__}: {str(exc)[:80]}")
        if feats is None:
            fail += 1
        else:
            ok += 1
        if i % 25 == 0:
            print(f"  {i}/{len(todo)} (ok={ok} fail={fail})")

    # backfill _difficulty for previously cached features (no re-download)
    need = []
    for path in ds.feat_dir.glob("*.json"):
        f = json.loads(path.read_text("utf-8"))
        if "_difficulty" not in f:
            need.append(int(path.stem))
    if need:
        print(f"backfilling label for {len(need)} cached charts")
        for meta in client.get_charts(need):
            try:
                ds.get_features(meta)
            except Exception:  # noqa: BLE001
                pass

    samples, ids, skipped = ds.collect_from_cache()
    print(f"\ncache now: {len(samples)} usable samples (skipped {skipped})")
    print(f"new downloads: ok={ok} fail={fail}")
    OUT.write_text(json.dumps(sorted(ids)), "utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
