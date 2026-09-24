"""Line features, restricted to RPE charts only.

`chart.lines` (and thus line_speed_p90 / line_rot_p90 / hidden_frac) is built for
RPE charts alone; other formats report 0, which dilutes any real signal in the
all-format test.  This re-runs the test on the RPE subset only.
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

CAND = {
    "line_speed_p90": lambda r: r["line_speed_p90"],
    "line_rot_p90": lambda r: r["line_rot_p90"],
    "hidden_frac": lambda r: r["hidden_frac"],
    "log_line_speed": lambda r: math.log1p(r["line_speed_p90"]),
    "log_line_rot": lambda r: math.log1p(r["line_rot_p90"]),
    "static_nps": lambda r: r["nps_peak"] / (1.0 + r["line_speed_p90"]),
}

allrows = []
for path in glob.glob("data/features/*.json"):
    cid = int(Path(path).stem)
    if cid not in CLEAN:
        continue
    f = json.loads(open(path, encoding="utf-8").read())
    if not all(k in f for k in FEATURE_NAMES):
        continue
    f["_id"] = cid
    allrows.append(f)

from collections import Counter
print("format mix in the cleaned set:", Counter(r.get("_format", "?") for r in allrows))
rows = [r for r in allrows if r.get("_format") == "rpe"]
print(f"RPE-only samples: {len(rows)}")


def samples(extra=()):
    out = []
    for r in rows:
        feats = {n: float(r[n]) for n in FEATURE_NAMES}
        for name in extra:
            feats[name] = float(CAND[name](r))
        out.append((feats, float(r["_difficulty"])))
    return out


def mean_cv(extra):
    best, alpha = -9.9, None
    for a in ALPHAS:
        v = float(np.mean([cross_val_r2(samples(extra), alpha=a,
                                         names=list(FEATURE_NAMES) + list(extra), seed=s)
                           for s in SEEDS]))
        if v > best:
            best, alpha = v, a
    return best, alpha


cv0, a0 = mean_cv([])
print(f"RPE-only baseline CV R2 = {cv0:.3f} @alpha={a0}")
print("\none-at-a-time:")
for cand in CAND:
    cv, a = mean_cv([cand])
    print(f"  +{cand:16s} CV R2={cv:.3f} ({cv - cv0:+.3f})")

cur, cv = [], cv0
print("\nforward selection:")
while True:
    trials = [(mean_cv(cur + [c]), c) for c in CAND if c not in cur]
    if not trials:
        break
    (tcv, ta), cand = max(trials)
    print(f"  best try {cand:16s} CV R2={tcv:.3f} ({tcv - cv:+.3f})")
    if tcv > cv + GAIN:
        cur.append(cand)
        cv = tcv
        print(f"  ADOPT {cand} -> CV R2={cv:.3f}")
    else:
        print("  stop")
        break
print(f"final extras: {cur}  CV R2={cv:.3f}")

ls = np.asarray([r["line_speed_p90"] for r in rows])
res0 = np.asarray([fit_difficulty_model(samples(), alpha=a0).predict_features(f)
                   for f, _ in samples()]) - np.asarray([d for _, d in samples()])
edges = np.percentile(ls, (0, 20, 40, 60, 80, 100))
edges[-1] += 1e-9
print("\nRPE-only residual by line_speed_p90 quintile (baseline model):")
for i in range(5):
    m = (ls >= edges[i]) & (ls < edges[i + 1])
    if m.sum():
        print(f"  [{edges[i]:7.2f},{edges[i+1]:7.2f}) n={m.sum():4d} mean resid={res0[m].mean():+6.3f}")
