"""Population (IRT-style) chart difficulty from real play records.

Model, fitted by ridge least squares on real records::

    log(无暇度_ij) = mu + theta_i (player imprecision) + b_j (chart timing difficulty)

``b_j`` is therefore an objective, unified per-chart difficulty derived purely
from how precisely real players can time the chart, independent of the
charter's own 定数.  We then compare it against 定数 and the feature-based D*.
"""

import collections
import json
import math
import sys

import numpy as np

from phira_pp.api import PhiraClient
from phira_pp.dataset import Dataset, load_model

OUT = "data/irt_difficulty.json"


def main(limit: int = 40, max_recs: int = 60, alpha: float = 1.0):
    client = PhiraClient()
    ds = Dataset(client=client)
    model = load_model("data/difficulty_model.json")

    rows = []
    for meta in ds.iter_ranked_metas(limit):
        feats = ds.get_features(meta)
        if not feats:
            continue
        d_star = model.predict_features(feats)
        for r in client.iter_chart_records(meta.id, max_records=max_recs):
            if r.miss != 0 or r.accuracy < 0.99 or not (0 < r.std <= 0.2):
                continue
            rows.append((r.player, meta.id, math.log(r.std), meta.difficulty, d_star))

    if len(rows) < 50:
        print(f"not enough clean records: {len(rows)}")
        return

    players = sorted({r[0] for r in rows})
    charts = sorted({r[1] for r in rows})
    pidx = {p: i for i, p in enumerate(players)}
    cidx = {c: j for j, c in enumerate(charts)}
    n = len(rows)
    ncol = 1 + len(players) + len(charts)

    # Identification diagnostics: the model can only separate player ability from
    # chart difficulty when players appear on multiple charts.
    per_player = collections.Counter(r[0] for r in rows)
    per_chart = collections.Counter(r[1] for r in rows)
    multi = sum(1 for p, c in per_player.items() if c >= 2)
    print(f"records/player: mean={n/len(players):.2f} max={max(per_player.values())} "
          f"players_with>=2={multi}/{len(players)} ({multi/len(players):.1%})")
    print(f"records/chart: mean={n/len(charts):.1f} min={min(per_chart.values())} "
          f"max={max(per_chart.values())}")
    print(f"parameters: players={len(players)} + charts={len(charts)} for {n} records")

    a = np.zeros((n, ncol))
    y = np.zeros(n)
    for k, (player, chart, log_std, _, _) in enumerate(rows):
        a[k, 0] = 1.0
        a[k, 1 + pidx[player]] = 1.0
        a[k, 1 + len(players) + cidx[chart]] = 1.0
        y[k] = log_std

    reg = np.eye(ncol) * alpha
    reg[0, 0] = 0.0
    coef = np.linalg.solve(a.T @ a + reg, a.T @ y)
    b = coef[1 + len(players):]

    print(f"records={n}  players={len(players)}  charts={len(charts)}")
    pred = a @ coef
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    print(f"in-sample R2 on log(无暇度): {1 - ss_res/ss_tot:.3f}")

    chart_difficulty = {r[1]: r[3] for r in rows}
    chart_dstar = {r[1]: r[4] for r in rows}
    dif = np.asarray([chart_difficulty[c] for c in charts])
    dst = np.asarray([chart_dstar[c] for c in charts])

    # b is in log-seconds; its spread is the multiplicative difficulty range
    print(f"b_j spread: std={b.std():.3f} (log)  -> x{math.exp(b.std()):.2f} in ms")
    print(f"corr(b_j, 定数)   = {np.corrcoef(b, dif)[0,1]:+.3f}")
    print(f"corr(b_j, D*)    = {np.corrcoef(b, dst)[0,1]:+.3f}")
    print(f"corr(定数, D*)    = {np.corrcoef(dif, dst)[0,1]:+.3f}")

    order = np.argsort(b)[::-1]
    print("hardest by b_j (chart, 定数, D*, ms factor):")
    for j in order[:6]:
        print(f"  #{charts[j]:<8d} 定数={dif[j]:5.1f} D*={dst[j]:5.2f} "
              f"x{math.exp(b[j] - b.mean()):.2f}")
    print("easiest by b_j:")
    for j in order[-6:]:
        print(f"  #{charts[j]:<8d} 定数={dif[j]:5.1f} D*={dst[j]:5.2f} "
              f"x{math.exp(b[j] - b.mean()):.2f}")

    payload = {
        "charts": {str(c): float(b[j] - b.mean()) for j, c in enumerate(charts)},
        "meta": {"records": n, "players": len(players), "charts": len(charts)},
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    print("saved ->", OUT)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 40)
