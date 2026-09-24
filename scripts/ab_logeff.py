"""Controlled A/B: log_notes (raw keys) vs log_eff (press-weighted 物量).

Both columns are present in the v7 cache, so this compares them on ONE fixed
cleaned set with one fixed alpha and identical folds/seeds — no protocol noise.
Reports plain CV R2 and a nested CV whose trim is re-derived inside each fold.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import numpy as np

from phira_pp.difficulty import fit_difficulty_model
from phira_pp.features import FEATURE_NAMES

ALPHA = 30.0
TRIM = 2.5
DMIN = 1.0
SEEDS = (0, 1, 2, 3, 4)
FOLDS = 5
CLEAN_IDS = Path("data/train_clean_ids.json")

rows = []
for path in glob.glob("data/features/*.json"):
    f = json.loads(open(path, encoding="utf-8").read())
    if f.get("_version") != 7 or "_difficulty" not in f:
        continue
    if not all(k in f for k in FEATURE_NAMES):
        continue
    if f["_difficulty"] < DMIN:
        continue
    f["_id"] = int(Path(path).stem)
    rows.append(f)

# one fixed cleaned set, derived with the raw-key feature (the v1 protocol)
BASE = [n for n in FEATURE_NAMES if n != "log_eff"] + ["log_notes"]
s_all = [({n: float(r[n]) for n in BASE}, float(r["_difficulty"])) for r in rows]
m0 = fit_difficulty_model(s_all, alpha=ALPHA, names=BASE)
pred = np.asarray([m0.predict_features(f) for f, _ in s_all])
y = np.asarray([d for _, d in s_all])
r0 = pred - y
med, sig = float(np.median(r0)), 1.4826 * float(np.median(np.abs(r0 - np.median(r0))))
keep = np.abs(r0 - med) <= TRIM * sig
rows_clean = [r for r, ok in zip(rows, keep) if ok]
print(f"fixed cleaned set: {len(rows_clean)} charts (sigma={sig:.2f})")


def feats(r, use_eff):
    names = [n for n in FEATURE_NAMES if n != "log_eff"] + (["log_eff"] if use_eff else ["log_notes"])
    return {n: float(r[n]) for n in names}


def cv(use_eff, nested):
    samples = [(feats(r, use_eff), float(r["_difficulty"])) for r in rows_clean]
    names = BASE if not use_eff else [n for n in FEATURE_NAMES]
    scores = []
    for seed in SEEDS:
        idx = np.random.default_rng(seed).permutation(len(samples))
        chunks = np.array_split(idx, FOLDS)
        for k in range(FOLDS):
            train = [samples[i] for j in range(FOLDS) if j != k for i in chunks[j]]
            test = [samples[i] for i in chunks[k]]
            if nested:
                mm = fit_difficulty_model(train, alpha=ALPHA, names=names)
                rr = np.asarray([mm.predict_features(f) for f, _ in train]) - np.asarray([d for _, d in train])
                md, sg = float(np.median(rr)), 1.4826 * float(np.median(np.abs(rr - np.median(rr))))
                train = [s for s, okk in zip(train, np.abs(rr - md) <= TRIM * sg) if okk]
            if len(train) < len(names) + 2:
                continue
            m = fit_difficulty_model(train, alpha=ALPHA, names=names)
            p = np.asarray([m.predict_features(f) for f, _ in test])
            yy = np.asarray([d for _, d in test])
            tot = float(((yy - yy.mean()) ** 2).sum())
            if tot > 0:
                scores.append(1.0 - float(((p - yy) ** 2).sum()) / tot)
    return float(np.mean(scores))


print(f"\nalpha = {ALPHA}, {FOLDS}-fold x {len(SEEDS)} seeds")
for use_eff, label in ((False, "log_notes (raw keys)"), (True, "log_eff (press-weighted)")):
    print(f"  {label:26s} plain CV R2 = {cv(use_eff, False):.3f}   "
          f"nested CV R2 = {cv(use_eff, True):.3f}")

print("\nalso at alpha = 10 and 100 (plain CV):")
for a in (10.0, 100.0):
    globals()["ALPHA"] = a
    print(f"  alpha={a:6.1f}  log_notes={cv(False, False):.3f}  log_eff={cv(True, False):.3f}")
