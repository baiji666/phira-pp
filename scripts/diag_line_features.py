"""Would judge-line features fix the residual trend found by diag_line_bias.py?

Tests the cached line features and a few derived candidates (incl. the
"static line but dense" interaction) with the same CV protocol, on the cleaned
label set.  Only CV-improving features may be adopted.
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

DERIVED = {
    "line_speed_p90": lambda r: r["line_speed_p90"],
    "line_rot_p90": lambda r: r["line_rot_p90"],
    "hidden_frac": lambda r: r["hidden_frac"],
    "log_line_speed": lambda r: math.log1p(r["line_speed_p90"]),
    "log_line_rot": lambda r: math.log1p(r["line_rot_p90"]),
    "static_nps": lambda r: r["nps_peak"] / (1.0 + r["line_speed_p90"]),
    "linemove_x_nps": lambda r: r["line_speed_p90"] * r["nps_peak"],
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


def samples(extra=()):
    out = []
    for r in rows:
        feats = {n: float(r[n]) for n in FEATURE_NAMES}
        for name in extra:
            feats[name] = float(DERIVED[name](r))
        out.append((feats, float(r["_difficulty"])))
    return out


def mean_cv(extra):
    best, alpha = -9.9, None
    for a in ALPHAS:
        v = float(np.mean([cross_val_r2(samples(extra), alpha=a, names=list(FEATURE_NAMES) + list(extra),
                                         seed=s) for s in SEEDS]))
        if v > best:
            best, alpha = v, a
    return best, alpha


cv0, a0 = mean_cv(())
print(f"baseline CV R2 = {cv0:.3f} @alpha={a0}")

print("\none-at-a-time gain:")
gains = []
for cand in DERIVED:
    cv, a = mean_cv([cand])
    gains.append((cv - cv0, cv, cand, a))
    print(f"  +{cand:16s} CV R2={cv:.3f} ({cv - cv0:+.3f})")

cur = []
cv = cv0
print("\nforward selection:")
while True:
    remaining = [c for c in DERIVED if c not in cur]
    trials = []
    for cand in remaining:
        tcv, ta = mean_cv(cur + [cand])
        trials.append((tcv, ta, cand))
    trials.sort(reverse=True)
    tcv, ta, cand = trials[0]
    print(f"  best try {cand:16s} CV R2={tcv:.3f} ({tcv - cv:+.3f})")
    if tcv > cv + GAIN:
        cur.append(cand)
        cv = tcv
        print(f"  ADOPT {cand} -> CV R2={cv:.3f} @alpha={ta}")
    else:
        print("  stop")
        break

print(f"\nfinal extra features: {cur}  CV R2={cv:.3f}")

# what do the adopted ones look like as weights / do they flatten the trend?
if cur:
    s = samples(cur)
    m = fit_difficulty_model(s, alpha=ta)
    print("weights on the adopted extras:")
    for n, w in zip(m.names, m.weights):
        if n in cur:
            print(f"    {n:16s} {w:+.3f}")
    res = np.asarray([m.predict_features(f) for f, _ in s]) - np.asarray([d for _, d in s])
    ls = np.asarray([r["line_speed_p90"] for r in rows])
    edges = np.percentile(ls, (0, 20, 40, 60, 80, 100))
    edges[-1] += 1e-9
    print("residual by line_speed quintile after the fix:")
    for i in range(5):
        mm = (ls >= edges[i]) & (ls < edges[i + 1])
        if mm.sum():
            print(f"  [{edges[i]:7.2f},{edges[i+1]:7.2f}) n={mm.sum():4d} mean resid={res[mm].mean():+6.3f}")
