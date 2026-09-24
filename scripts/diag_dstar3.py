"""Decide the D* fix, all by cross-validation:

  1. baseline on the real training floor (labels 0.0 are Phira's "unset" marker),
  2. robust residual trim — drop labels inconsistent with the chart's features,
  3. forward feature selection (incl. the new orderliness features) on the trimmed set.

Only CV-improving steps are reported as adoptable.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import numpy as np

from phira_pp.difficulty import cross_val_r2, fit_difficulty_model
from phira_pp.features import CANDIDATE_FEATURES, FEATURES_VERSION, FEATURE_NAMES

ALPHAS = (3.0, 10.0, 30.0, 100.0)
SEEDS = (0, 1, 2, 3, 4)
ALL_COLS = FEATURE_NAMES + CANDIDATE_FEATURES
DMIN = 1.0          # 0.0 is a placeholder, not a difficulty
TRIM = 2.5          # robust-sigma multiplier
MIN_GAIN = 0.010


def load_rows():
    rows = []
    for path in glob.glob("data/features/*.json"):
        try:
            f = json.loads(open(path, encoding="utf-8").read())
        except Exception:  # noqa: BLE001
            continue
        if f.get("_version") != FEATURES_VERSION or "_difficulty" not in f:
            continue
        if not all(k in f for k in ALL_COLS):
            continue
        if f["_difficulty"] < DMIN:
            continue
        f["_id"] = int(Path(path).stem)
        rows.append(f)
    return rows


def samples_of(rows, names):
    return [({n: float(r[n]) for n in names}, float(r["_difficulty"])) for r in rows]


def mean_cv(samples, names):
    best, alpha = -9.9, None
    for a in ALPHAS:
        v = float(np.mean([cross_val_r2(samples, alpha=a, names=names, seed=s) for s in SEEDS]))
        if v > best:
            best, alpha = v, a
    return best, alpha


rows = load_rows()
base = list(FEATURE_NAMES)
ys_all = np.asarray([r["_difficulty"] for r in rows])
print(f"n={len(rows)}  labels {ys_all.min():.1f}-{ys_all.max():.1f}")

s = samples_of(rows, base)
cv0, a0 = mean_cv(s, base)
print(f"baseline CV R2 = {cv0:.3f} @alpha={a0}")

model = fit_difficulty_model(s, alpha=a0, names=base)
pred = np.asarray([model.predict_features(f) for f, _ in s])
res = pred - np.asarray([d for _, d in s])
med = float(np.median(res))
sigma = 1.4826 * float(np.median(np.abs(res - med)))
keep = np.abs(res - med) <= TRIM * sigma
dropped = np.where(~keep)[0]
print(f"\nrobust sigma(定数) = {sigma:.2f} -> drop {len(dropped)}/{len(rows)} charts")
for i in dropped[:35]:
    print(f"    #{rows[i]['_id']:<7d} label={rows[i]['_difficulty']:<6} pred={pred[i]:5.2f} "
          f"resid={res[i]:+6.2f} ranked={rows[i].get('_ranked')} nps={rows[i]['nps_peak']:.0f}")

rows2 = [r for i, r in enumerate(rows) if keep[i]]
s2 = samples_of(rows2, base)
cv1, a1 = mean_cv(s2, base)
print(f"\ntrimmed: n={len(rows2)}  baseline CV R2 = {cv1:.3f} @alpha={a1}  ({cv1 - cv0:+.3f})")

cur, cv, alpha = list(base), cv1, a1
remaining = [c for c in CANDIDATE_FEATURES if c not in cur]
print("\nforward selection (trimmed set):")
while remaining:
    trials = []
    for cand in remaining:
        tcv, ta = mean_cv(samples_of(rows2, cur + [cand]), cur + [cand])
        trials.append((tcv, ta, cand))
    trials.sort(reverse=True)
    tcv, ta, cand = trials[0]
    print(f"  best try {cand:20s} CV R2={tcv:.3f} ({tcv - cv:+.3f})")
    if tcv > cv + MIN_GAIN:
        cur.append(cand)
        cv, alpha = tcv, ta
        remaining.remove(cand)
        print(f"  ADOPT {cand}  ->  CV R2={cv:.3f} ({len(cur)} feats) @alpha={alpha}")
    else:
        print("  no candidate passes the threshold; stop")
        break

print(f"\nFINAL features ({len(cur)}): {cur}")
print(f"FINAL CV R2 = {cv:.3f} @alpha={alpha}")
m2 = fit_difficulty_model(s2, alpha=alpha, names=cur)
p2 = np.asarray([m2.predict_features(f) for f, _ in s2])
y2 = np.asarray([d for _, d in s2])
print(f"trimmed in-sample RMSE = {np.sqrt(((p2 - y2) ** 2).mean()):.3f}")
print("weights (by |w|):")
for n, w in sorted(zip(m2.names, m2.weights), key=lambda t: -abs(t[1])):
    print(f"    {n:20s} {w:+.3f}")
