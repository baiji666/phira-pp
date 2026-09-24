"""Is D* really "density = difficulty"?  Diagnose with cross-validation.

Compares, on the same cached samples and the same CV protocol:
  * the current feature set (baseline),
  * each candidate feature, including the new "orderliness" ones,
  * label-hygiene variants (all labels vs. trustworthy-only labels).
Only CV-improving features may be adopted.
"""

from __future__ import annotations

import glob
import json

import numpy as np

from phira_pp.difficulty import cross_val_r2, fit_difficulty_model
from phira_pp.features import CANDIDATE_FEATURES, FEATURES_VERSION, FEATURE_NAMES

ALPHAS = (3.0, 10.0, 30.0, 100.0)
SEEDS = (0, 1, 2, 3, 4)
ALL_COLS = FEATURE_NAMES + CANDIDATE_FEATURES


def load_rows():
    rows = []
    bad = 0
    for path in glob.glob("data/features/*.json"):
        try:
            f = json.loads(open(path, encoding="utf-8").read())
        except Exception:  # noqa: BLE001
            bad += 1
            continue
        if f.get("_version") != FEATURES_VERSION or "_difficulty" not in f:
            bad += 1
            continue
        if not all(k in f for k in ALL_COLS):
            bad += 1
            continue
        rows.append(f)
    print(f"usable cached charts: {len(rows)}  (skipped {bad})")
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
ys = np.asarray([r["_difficulty"] for r in rows])
print(f"定数 labels: min={ys.min():.1f} p10={np.percentile(ys,10):.1f} "
      f"median={np.median(ys):.1f} p90={np.percentile(ys,90):.1f} max={ys.max():.1f}")
n_ranked = sum(1 for r in rows if r.get("_ranked"))
print(f"  ranked labels: {n_ranked}   non-ranked: {len(rows) - n_ranked}"
      f"   labels <10: {int((ys < 10).sum())}   labels <5: {int((ys < 5).sum())}")

base = list(FEATURE_NAMES)
samples = samples_of(rows, base)

print("\n--- baseline (current features, all labels) ---")
cv0, a0 = mean_cv(samples, base)
print(f"CV R2 = {cv0:.3f} @alpha={a0}   (n={len(samples)})")

model = fit_difficulty_model(samples, alpha=a0, names=base)
pred = np.asarray([model.predict_features(f) for f, _ in samples])
print(f"in-sample R2={1 - ((pred-ys)**2).sum()/((ys-ys.mean())**2).sum():.3f} "
      f"RMSE={np.sqrt(((pred-ys)**2).mean()):.3f}")
print("standardised weights (by |w|):")
for n, w in sorted(zip(model.names, model.weights), key=lambda t: -abs(t[1])):
    print(f"    {n:18s} {w:+.3f}")

print("\n--- feature vs label correlation ---")
for n in base:
    col = np.asarray([r[n] for r in rows])
    print(f"    {n:18s} r={np.corrcoef(col, ys)[0,1]:+.3f}")

print("\n--- candidate features: one-at-a-time CV gain ---")
for cand in CANDIDATE_FEATURES:
    cv, a = mean_cv(samples_of(rows, base + [cand]), base + [cand])
    print(f"    +{cand:20s} CV R2={cv:.3f} ({cv-cv0:+.3f}) @alpha={a}")

print("\n--- label hygiene (baseline features) ---")
variants = {
    "all labels": rows,
    "ranked only": [r for r in rows if r.get("_ranked")],
    "label >= 10": [r for r in rows if r["_difficulty"] >= 10],
    "label >= 5 (drop junk)": [r for r in rows if r["_difficulty"] >= 5],
    "ranked OR label>=13": [r for r in rows
                            if r.get("_ranked") or r["_difficulty"] >= 13],
}
for label, subset in variants.items():
    if len(subset) < len(base) + 20:
        print(f"    {label:24s} n={len(subset):4d}  (too few)")
        continue
    s = samples_of(subset, base)
    cv, a = mean_cv(s, base)
    print(f"    {label:24s} n={len(subset):4d}  CV R2={cv:.3f} @alpha={a}")
