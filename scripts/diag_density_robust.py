"""Is `nps_peak` (a raw per-window max) poisoned by outliers?

#54540 reports nps_peak = 7376 — an absurd value produced by stacked drags —
and the feature's fitted weight is a useless -0.024.  Tests robust density
measures (shorter windows, and a gap-based speed) against the baseline.
"""

from __future__ import annotations

import glob
import json
import math
from pathlib import Path

import numpy as np

from phira_pp.difficulty import cross_val_r2, fit_difficulty_model
from phira_pp.features import FEATURE_NAMES

ALPHAS = (3.0, 10.0, 30.0, 100.0)
SEEDS = (0, 1, 2, 3, 4)
GAIN = 0.010
CLEAN = set(json.loads(Path("data/train_clean_ids.json").read_text("utf-8")))

ADD = {
    "nps_peak_500": lambda r: r["nps_peak_500"],
    "nps_peak_025": lambda r: r["nps_peak_025"],
    "log_nps_500": lambda r: math.log10(1 + r["nps_peak_500"]),
    "log_inv_gap05": lambda r: math.log10(1 + 1.0 / max(1e-3, r["interval_p05"])),
}
REPLACE = {
    "nps_peak": {"use_500": lambda r: {"nps_peak_500": r["nps_peak_500"]},
                 "use_025": lambda r: {"nps_peak_025": r["nps_peak_025"]},
                 "use_log500": lambda r: {"log_nps_500": math.log10(1 + r["nps_peak_500"])}},
}

rows = []
for path in glob.glob("data/features/*.json"):
    cid = int(Path(path).stem)
    if cid not in CLEAN:
        continue
    f = json.loads(open(path, encoding="utf-8").read())
    if not all(k in f for k in FEATURE_NAMES):
        continue
    f["_id"] = cid
    rows.append(f)
print(f"cleaned samples: {len(rows)}")
print("nps_peak distribution: " +
      "  ".join(f"p{p}={np.percentile([r['nps_peak'] for r in rows], p):.0f}"
                for p in (50, 90, 99, 100)))
print("nps_peak > 1000 charts: " +
      str(sorted((r["_id"], round(r["nps_peak"])) for r in rows if r["nps_peak"] > 1000)))


def build(extra=(), repl=None, drop=()):
    names = [n for n in FEATURE_NAMES if n not in drop]
    names = names + (list(repl(rows[0]).keys()) if repl else []) + list(extra)
    out = []
    for r in rows:
        feats = {n: float(r[n]) for n in FEATURE_NAMES if n not in drop}
        if repl:
            feats.update({k: float(v) for k, v in repl(r).items()})
        for a in extra:
            feats[a] = float(ADD[a](r))
        out.append((feats, float(r["_difficulty"])))
    return out, names


def mean_cv(extra=(), repl=None, drop=()):
    s, names = build(extra, repl, drop)
    best, alpha = -9.9, None
    for a in ALPHAS:
        v = float(np.mean([cross_val_r2(s, alpha=a, names=names, seed=sd) for sd in SEEDS]))
        if v > best:
            best, alpha = v, a
    return best, alpha


cv0, a0 = mean_cv()
print(f"\nbaseline CV R2 = {cv0:.3f} @alpha={a0}")
print("\nadd one:")
for a in ADD:
    cv, _ = mean_cv(extra=[a])
    print(f"  +{a:14s} {cv:.3f} ({cv - cv0:+.3f})")
print("\nreplace nps_peak:")
for label, fn in REPLACE["nps_peak"].items():
    cv, _ = mean_cv(repl=fn, drop=("nps_peak",))
    print(f"  {label:12s} {cv:.3f} ({cv - cv0:+.3f})")
print("\nadd robust density on top of the winner:")
best_label, best_cv = max(((l, mean_cv(repl=f, drop=("nps_peak",))[0])
                           for l, f in REPLACE["nps_peak"].items()), key=lambda t: t[1])
print(f"  (winner {best_label} = {best_cv:.3f})")

# does a robust density restore a meaningful nps weight?
s, names = build(repl=REPLACE["nps_peak"][best_label], drop=("nps_peak",))
m = fit_difficulty_model(s, alpha=a0, names=names)
print("\nweights for density-ish terms after the swap:")
for n, w in zip(names, m.weights):
    if "nps" in n or "gap" in n or n in ("aim_p99", "aim_mean", "log_notes", "log_duration"):
        print(f"    {n:16s} {w:+.3f}")
