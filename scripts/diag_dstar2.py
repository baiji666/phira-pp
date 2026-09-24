"""Part 2: are the low labels junk, and do orderliness features help once the
labels are cleaned?"""

from __future__ import annotations

import glob
import json

import numpy as np

from phira_pp.difficulty import cross_val_r2, fit_difficulty_model
from phira_pp.features import CANDIDATE_FEATURES, FEATURES_VERSION, FEATURE_NAMES

ALPHAS = (3.0, 10.0, 30.0, 100.0)
SEEDS = (0, 1, 2, 3, 4)
ALL_COLS = FEATURE_NAMES + CANDIDATE_FEATURES
PROFILE = ("log_notes", "nps_peak", "aim_mean", "multi_frac", "hold_frac", "chord_mean")


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
        f["_id"] = int(path.split("\\")[-1].split("/")[-1].split(".")[0])
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
low = [r for r in rows if r["_difficulty"] < 10]
mid = [r for r in rows if 14.0 <= r["_difficulty"] <= 16.0]
print(f"label<10: n={len(low)}    label 14-16: n={len(mid)}")
print(f"{'feature':14s} {'<10 mean':>10} {'14-16 mean':>11}   ratio")
for name in PROFILE:
    a = np.asarray([r[name] for r in low])
    b = np.asarray([r[name] for r in mid])
    ratio = a.mean() / b.mean() if b.mean() else float("nan")
    print(f"  {name:12s} {a.mean():10.3f} {b.mean():11.3f}   {ratio:5.2f}")
print("label<10 ids:", sorted(r["_id"] for r in low))

base = list(FEATURE_NAMES)
for lo in (0.0, 8.0, 10.0, 12.0):
    subset = [r for r in rows if r["_difficulty"] >= lo]
    if len(subset) < 60:
        continue
    s = samples_of(subset, base)
    cv0, a0 = mean_cv(s, base)
    print(f"\n=== labels >= {lo:.0f}: n={len(subset)}  baseline CV R2={cv0:.3f} @alpha={a0}")
    gains = []
    for cand in CANDIDATE_FEATURES:
        cv, a = mean_cv(samples_of(subset, base + [cand]), base + [cand])
        gains.append((cv - cv0, cv, cand))
    for gain, cv, cand in sorted(gains, reverse=True)[:6]:
        print(f"    +{cand:20s} CV R2={cv:.3f} ({gain:+.3f})")
