"""Density saturation: is D* linear where it should be concave?

The worst overestimates are all extreme-density charts (nps 60-135), which is
what a linear term does at the top of the range.  Tests quadratic / log terms
(derived on the fly from cached features) with the usual CV protocol.
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

# name -> (how to build, feature replaced or added)
ADD = {
    "nps_sq": lambda r: r["nps_peak"] ** 2 / 100.0,
    "aim_p99_sq": lambda r: r["aim_p99"] ** 2 / 100.0,
    "aim_mean_sq": lambda r: r["aim_mean"] ** 2,
    "log_nps": lambda r: math.log1p(r["nps_peak"]),
    "log_aim_p99": lambda r: math.log1p(r["aim_p99"]),
    "nps_per_note": lambda r: r["nps_peak"] / max(1.0, r["_note_count"] / 1000.0),
}
REPLACE = {                       # swap a linear term for a saturating one
    "nps_peak": {"log_nps_only": lambda r: math.log1p(r["nps_peak"]),
                 "sqrt_nps_only": lambda r: math.sqrt(r["nps_peak"])},
    "aim_p99": {"log_aim_p99_only": lambda r: math.log1p(r["aim_p99"])},
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


def samples(extra=(), replace=()):
    names = [n for n in FEATURE_NAMES if n not in {r[0] for r in replace}]
    out = []
    for r in rows:
        feats = {n: float(r[n]) for n in names}
        for _old, newname, fn in replace:
            feats[newname] = float(fn(r))
        for name in extra:
            feats[name] = float(ADD[name](r))
        out.append((feats, float(r["_difficulty"])))
    return out


def names_of(extra=(), replace=()):
    base = [n for n in FEATURE_NAMES if n not in {r[0] for r in replace}]
    return base + [r[1] for r in replace] + list(extra)


def mean_cv(extra=(), replace=()):
    best, alpha = -9.9, None
    for a in ALPHAS:
        v = float(np.mean([cross_val_r2(samples(extra, replace), alpha=a,
                                         names=names_of(extra, replace), seed=s)
                           for s in SEEDS]))
        if v > best:
            best, alpha = v, a
    return best, alpha


cv0, a0 = mean_cv()
print(f"baseline CV R2 = {cv0:.3f} @alpha={a0}")

print("\nadd one saturating term:")
for name in ADD:
    cv, a = mean_cv([name])
    print(f"  +{name:14s} CV R2={cv:.3f} ({cv - cv0:+.3f})")

print("\nreplace a linear term:")
for old, opts in REPLACE.items():
    for label, fn in opts.items():
        cv, a = mean_cv((), [(old, label, fn)])
        print(f"  {label:18s} (replaces {old}) CV R2={cv:.3f} ({cv - cv0:+.3f})")

print("\nforward selection (add + replace):")
cur_add: list[str] = []
cur_rep: list[tuple] = []
cv = cv0
while True:
    trials = []
    for name in ADD:
        if name not in cur_add:
            tcv, ta = mean_cv(cur_add + [name], cur_rep)
            trials.append((tcv, ta, ("add", name)))
    for old, opts in REPLACE.items():
        if not any(r[0] == old for r in cur_rep):
            for label, fn in opts.items():
                tcv, ta = mean_cv(cur_add, cur_rep + [(old, label, fn)])
                trials.append((tcv, ta, ("rep", (old, label, fn))))
    if not trials:
        break
    trials.sort(reverse=True)
    tcv, ta, action = trials[0]
    tag = action[1] if action[0] == "add" else f"{action[1][1]} (for {action[1][0]})"
    print(f"  best try {tag:26s} CV R2={tcv:.3f} ({tcv - cv:+.3f})")
    if tcv > cv + GAIN:
        if action[0] == "add":
            cur_add.append(action[1])
        else:
            cur_rep.append(action[1])
        cv = tcv
        print(f"  ADOPT {tag} -> CV R2={cv:.3f} @alpha={ta}")
    else:
        print("  stop")
        break

print(f"\nfinal: extra={cur_add} replaced={[r[1] for r in cur_rep]}  CV R2={cv:.3f}")

s = samples(cur_add, cur_rep)
m = fit_difficulty_model(s, alpha=ta)
res = np.asarray([m.predict_features(f) for f, _ in s]) - np.asarray([d for _, d in s])
nps = np.asarray([r["nps_peak"] for r in rows])
edges = np.percentile(nps, (0, 20, 40, 60, 80, 100))
edges[-1] += 1e-9
print("residual by nps_peak quintile after the fix:")
for i in range(5):
    mm = (nps >= edges[i]) & (nps < edges[i + 1])
    if mm.sum():
        print(f"  [{edges[i]:7.1f},{edges[i+1]:7.1f}) n={mm.sum():4d} mean resid={res[mm].mean():+6.3f}")
