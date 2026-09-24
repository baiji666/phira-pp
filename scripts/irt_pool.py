"""Population IRT difficulty fitted on a CONNECTED player-chart graph.

Player data comes from each player's record pool (``/record/get-pool``), which
by construction gives overlapping players and charts.  The model is

    log(无暇度_ij) = mu + theta_i (player) + b_j (chart)

and ``b_j`` is the population-derived, unified chart difficulty.  We report its
correlation with the charter's 定数 (with significance) to decide whether it is
usable at all.

D* is only computed for charts whose features are already cached, to avoid
re-downloading packages.
"""

import collections
import json
import math
import sys

import numpy as np
from scipy import stats

from phira_pp.api import PhiraClient
from phira_pp.dataset import Dataset, load_model

OUT = "data/irt_difficulty.json"


def harvest_players(client, want, max_charts, per_chart=5):
    """Collect player ids across many charts.

    Taking only a few records per chart forces the harvest to traverse a wide
    range of charts, so the harvested players' pools span more of the catalogue.
    """
    players, seen = [], set()
    page = 1
    charts = 0
    while len(players) < want and charts < max_charts:
        data = client.search_charts(page=page, pageNum=30, order="rating", division="regular")
        rows = data.get("results") or data.get("result") or []
        if not rows:
            break
        for row in rows:
            if not (row.get("ranked") and row.get("reviewed")):
                continue
            charts += 1
            taken = 0
            for r in client.iter_chart_records(row["id"], max_records=per_chart):
                if r.player not in seen:
                    seen.add(r.player)
                    players.append(r.player)
                taken += 1
                if len(players) >= want or taken >= per_chart:
                    break
            if len(players) >= want or charts >= max_charts:
                break
        page += 1
    print(f"  harvested {len(players)} players from {charts} charts")
    return players


def main(n_players: int = 600, max_charts: int = 200, per_chart: int = 5,
         extra_charts: int = 80, alpha: float = 5.0):
    client = PhiraClient()
    ds = Dataset(client=client)
    model = load_model("data/difficulty_model.json")

    players = harvest_players(client, n_players, max_charts, per_chart=per_chart)
    print(f"harvested {len(players)} players")

    rows = []
    pending = []
    for i, pid in enumerate(players):
        try:
            pool = client.get_best_pool(pid)
        except Exception:  # noqa: BLE001
            continue
        pool_rows = pool.get("bestPool", pool if isinstance(pool, list) else [])
        for row in pool_rows:
            chart = row.get("chart")
            rid = row.get("record") or row.get("id")
            if chart is not None and rid is not None:
                pending.append((pid, chart, rid))
        if (i + 1) % 100 == 0:
            print(f"  pools {i+1}/{len(players)}")

    if pending:
        ids = [p[2] for p in pending]
        print(f"resolving {len(ids)} record ids")
        detail = {r.id: r for r in client.get_records(ids)}
        for pid, chart, rid in pending:
            r = detail.get(rid)
            if r and r.miss == 0 and r.accuracy >= 0.99 and 0 < r.std <= 0.2:
                rows.append((pid, chart, math.log(r.std)))

    if len(rows) < 100:
        print(f"not enough clean records: {len(rows)}")
        return

    # Add per-chart records to widen CHART coverage (pools provide connectivity,
    # these add breadth).  The record query returns 无暇度 directly.
    added = 0
    for meta in ds.iter_ranked_metas(extra_charts):
        try:
            recs = list(client.iter_chart_records(meta.id, max_records=30))
        except Exception:  # noqa: BLE001
            continue
        for r in recs:
            if r.miss == 0 and r.accuracy >= 0.99 and 0 < r.std <= 0.2:
                rows.append((r.player, meta.id, math.log(r.std)))
                added += 1
    print(f"added {added} records from up to {extra_charts} extra charts")

    chart_ids = sorted({r[1] for r in rows})
    players_u = sorted({r[0] for r in rows})
    pidx = {p: i for i, p in enumerate(players_u)}
    cidx = {c: j for j, c in enumerate(chart_ids)}
    n = len(rows)
    ncol = 1 + len(players_u) + len(chart_ids)

    per_player = collections.Counter(r[0] for r in rows)
    multi = sum(1 for _, c in per_player.items() if c >= 2)
    print(f"clean records={n} players={len(players_u)} charts={len(chart_ids)}")
    print(f"records/player: mean={n/len(players_u):.2f}  "
          f"players_with>=2_charts={multi}/{len(players_u)} ({multi/len(players_u):.1%})")

    a = np.zeros((n, ncol))
    y = np.zeros(n)
    for k, (p, c, ls) in enumerate(rows):
        a[k, 0] = 1.0
        a[k, 1 + pidx[p]] = 1.0
        a[k, 1 + len(players_u) + cidx[c]] = 1.0
        y[k] = ls
    reg = np.eye(ncol) * alpha
    reg[0, 0] = 0.0
    coef = np.linalg.solve(a.T @ a + reg, a.T @ y)
    b = coef[1 + len(players_u):]

    pred = a @ coef
    print(f"in-sample R2 on log(无暇度): {1 - ((y-pred)**2).sum()/((y-y.mean())**2).sum():.3f}")

    # Only use charts whose features are already cached (no downloads)
    cached = [c for c in chart_ids if ds.features_path(c).exists()]
    metas = {m.id: m for m in client.get_charts(cached)} if cached else {}

    dif, dst, bb = [], [], []
    for j, c in enumerate(chart_ids):
        meta = metas.get(c)
        if meta is None:
            continue
        feats = ds.get_features(meta)
        bb.append(b[j])
        dif.append(meta.difficulty)
        dst.append(model.predict_features(feats) if feats else np.nan)
    bb = np.asarray(bb)
    dif = np.asarray(dif)
    dst = np.asarray(dst)

    r_d, p_d = stats.pearsonr(bb, dif)
    print(f"charts with 定数: n={len(dif)}")
    print(f"corr(b_j, 定数) = {r_d:+.3f}  (p={p_d:.4f})")
    ok = ~np.isnan(dst)
    if ok.sum() > 3:
        r_s, p_s = stats.pearsonr(bb[ok], dst[ok])
        print(f"corr(b_j, D*)  = {r_s:+.3f}  (p={p_s:.4f}, n={int(ok.sum())})")
        r_c, p_c = stats.pearsonr(dif[ok], dst[ok])
        print(f"corr(定数, D*)  = {r_c:+.3f}  (p={p_c:.4f})")
    print(f"b_j ms factor range: x{math.exp(bb.min()-bb.mean()):.2f}-x{math.exp(bb.max()-bb.mean()):.2f}")

    order = np.argsort(bb)[::-1]
    print("hardest by b_j:")
    for k in order[:5]:
        print(f"  #{chart_ids[k]:<8d} 定数={dif[k]:5.1f} x{math.exp(bb[k]-bb.mean()):.2f}")
    print("easiest by b_j:")
    for k in order[-5:]:
        print(f"  #{chart_ids[k]:<8d} 定数={dif[k]:5.1f} x{math.exp(bb[k]-bb.mean()):.2f}")

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({"charts": {str(c): float(b[j] - b.mean()) for j, c in enumerate(chart_ids)},
                   "meta": {"records": n, "players": len(players_u), "charts": len(chart_ids),
                            "corr_with_charter": float(r_d), "p_value": float(p_d)}},
                  fh, indent=2)
    print("saved ->", OUT)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 600)
