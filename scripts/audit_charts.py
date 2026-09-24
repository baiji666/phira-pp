"""Per-chart audit for the ids the user flagged.

For each chart: metadata, the difficulty actually used (ranked / KV / D*), the
largest contributions to that D*, the raw feature values, and the user's own
best record on it (an "experienced difficulty" proxy).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from phira_pp.api import PhiraClient, _record_from_dict
from phira_pp.dataset import Dataset, load_model

USER = 459003
FLAGGED = {
    54540: "高估", 50333: "高估", 30942: "高估", 52597: "高估",
    22206: "低估", 53994: "低估", 73474: "稍有高估",
}
SHOW = ["log_notes", "log_duration", "nps_peak", "aim_p99", "aim_mean", "aim_p95",
        "dir_change_p80", "dt_cv", "multi_frac", "hold_frac", "flick_frac",
        "line_speed_p90", "line_rot_p90", "hidden_frac"]

model = load_model("data/difficulty_model.json")
client = PhiraClient()
ds = Dataset()
anchors = json.loads(Path("data/kv_diff.json").read_text("utf-8"))
kv = {int(r["id"]): float(r["difficulty"]) for r in anchors.get("rows", [])}

for cid, tag in FLAGGED.items():
    meta = client.get_chart(cid)
    feats = ds.get_features(meta)
    if not feats:
        print(f"#{cid} {tag}: features unavailable")
        continue
    d = model.predict_features(feats)
    z = (np.asarray([feats[n] for n in model.names], dtype=float) - model.mean) / model.std
    contrib = z * model.weights
    print(f"\n=== #{cid} [{tag}] {meta.name[:38]}  {meta.level}")
    print(f"    谱师定数(API)={meta.difficulty}  ranked={meta.ranked} reviewed={meta.reviewed} "
          f"rating={meta.rating:.1f}({meta.rating_count})  定数表={kv.get(cid, '-')}")
    print(f"    D* = {d:.2f}      (bias={model.bias:.2f})")
    print("    largest contributions to D*:")
    for n, c in sorted(zip(model.names, contrib), key=lambda t: -abs(t[1]))[:6]:
        print(f"      {n:18s} {c:+6.3f}   (value={feats[n]:.3f} z={z[model.names.index(n)]:+.2f} w={model.weights[model.names.index(n)]:+.3f})")
    print("    raw: " + "  ".join(f"{n}={feats[n]:.2f}" for n in SHOW))
    try:
        rows = client.query_player_chart(USER, cid)
        if rows:
            best = max(rows, key=lambda x: float(x.get("score") or 0))
            rec = _record_from_dict(best)
            print(f"    我(459003)最佳: score={rec.score} acc={rec.accuracy*100:.2f}% "
                  f"miss={rec.miss} std={rec.std*1000:.1f}ms n={rec.total_judged}")
        else:
            print("    我(459003)未游玩")
    except Exception as exc:  # noqa: BLE001
        print(f"    record lookup failed: {exc}")
