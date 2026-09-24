"""Calibrate the PP precision axis from real records.

Collects real play records and reports the empirical 无暇度 (``std``)
distribution.  The precision axis is then anchored to percentiles of that
distribution so its influence is BOUNDED, rather than an unbounded ratio.
"""

import json
import sys

import numpy as np

from phira_pp.api import PhiraClient
from phira_pp.dataset import Dataset, load_model

OUT = "data/pp_params.json"


def main(limit: int = 30, max_recs: int = 60):
    client = PhiraClient()
    ds = Dataset(client=client)
    model = load_model("data/difficulty_model.json")

    accs, stds, misses = [], [], []
    charts_used = 0
    for meta in ds.iter_ranked_metas(limit):
        feats = ds.get_features(meta)
        if not feats:
            continue
        charts_used += 1
        for r in client.iter_chart_records(meta.id, max_records=max_recs):
            accs.append(r.accuracy)
            stds.append(r.std)
            misses.append(r.miss)

    acc = np.asarray(accs)
    std = np.asarray(stds)
    miss = np.asarray(misses)
    print(f"records: {len(acc)} over {charts_used} charts")
    print(f"accuracy: median={np.median(acc):.4f}  share<1.0={float((acc < 1-1e-9).mean()):.3f} "
          f"share<0.99={float((acc < 0.99).mean()):.3f}")

    clean = (acc >= 0.99) & (miss == 0) & (std > 0)
    s = std[clean] * 1000.0
    print(f"无暇度 (clean, acc>=0.99, no miss): n={s.size}")
    pcts = {p: float(np.percentile(s, p)) for p in (5, 10, 25, 50, 75, 90, 95)}
    for p, v in pcts.items():
        print(f"  p{p:<3d} = {v:6.2f} ms")
    print(f"  min={s.min():.2f}  max={s.max():.2f}")

    lo, hi = pcts[10] / 1000.0, pcts[90] / 1000.0
    params = {
        "precision_lo": lo,
        "precision_hi": hi,
        "precision_median": pcts[50] / 1000.0,
        "source": f"{int(s.size)} clean records over {charts_used} ranked charts",
        "percentiles_ms": pcts,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(params, fh, indent=2, ensure_ascii=False)

    print(f"\nanchors: precision_lo(p10)={lo*1000:.2f}ms  precision_hi(p90)={hi*1000:.2f}ms")
    print("implied bounded factor range (lo..hi) by weight:")
    for w in (0.15, 0.20, 0.25, 0.30):
        print(f"  weight={w:.2f}: factor {1-w/2:.3f}..{1+w/2:.3f}  -> max PP ratio {(1+w/2)/(1-w/2):.3f}")
    print("saved ->", OUT)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 30)
