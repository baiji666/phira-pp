r"""Forward selection for the PPSR-style segment features (audit item 2).

The reference model spends 34.6% of its splits on segment aggregation; we had
only chart-wide averages plus a 1 s density peak, which cannot tell a 9-minute
endurance chart from a 51-second burst.  Candidates (10 s windows, 5 s step,
plus an end-aligned window): seg_nps_p50/p90/max (press-weighted NPS) and
seg_speed_p95_mean/max.

Protocol matches scripts/fit_difficulty2.py: trim with the raw-key reference
model, drop degenerate charts, add the subjective table labels, alpha fixed at
30, same folds.  A candidate is adopted only if it raises CV R2.

    $env:PYTHONPATH="."; .\.venv\Scripts\python.exe scripts/exp_segment.py
"""

from __future__ import annotations

import glob
import json

import numpy as np

from phira_pp.difficulty import fit_difficulty_model
from phira_pp.features import CANDIDATE_FEATURES, FEATURES_VERSION, FEATURE_NAMES

ALPHA = 30.0
TRIM = 2.5
DMIN = 1.0
SEEDS = (0, 1, 2, 3, 4)
LE_HINGE = 3.4
HINGE_NAME = "le_hinge"
PREV = [n for n in FEATURE_NAMES if n != "seg_nps_p90"]
BASE_NAMES = PREV + [HINGE_NAME]
HINGES = {HINGE_NAME: ("log_eff", LE_HINGE)}
CAND = ["seg_nps_p50", "seg_nps_p90", "seg_nps_max",
        "seg_speed_p95_mean", "seg_speed_p95_max"]
BASE = [n for n in FEATURE_NAMES if n != "log_eff"] + ["log_notes"]
ALL = FEATURE_NAMES + CAND + ["log_notes"]
WATCH = (22206, 39209, 3007, 54540)
FEATS_ALL = FEATURE_NAMES + CAND


def vfeat(cid):
    return {n: float(rows[cid][n]) for n in FEATS_ALL}


def load():
    rows = {}
    for p in glob.glob("data/features/*.json"):
        try:
            f = json.loads(open(p, encoding="utf-8").read())
        except Exception:  # noqa: BLE001
            continue
        if f.get("_version") != FEATURES_VERSION or not all(k in f for k in ALL):
            continue
        if isinstance(f.get("_difficulty"), (int, float)):
            rows[int(p.split("\\")[-1].split("/")[-1].split(".")[0])] = f
    return rows


rows = load()
table = {r["id"]: r["difficulty"] for r in
         json.loads(open("data/subjective_diff.json", encoding="utf-8").read())["rows"]}
print(f"cached charts with all columns: {len(rows)}")

ordered = [c for c, f in rows.items() if c not in table and f["_difficulty"] >= DMIN]
ref = fit_difficulty_model([({n: float(rows[c][n]) for n in BASE}, float(rows[c]["_difficulty"]))
                            for c in ordered], alpha=ALPHA, names=BASE)
r0 = np.asarray([ref.predict_features({n: float(rows[c][n]) for n in BASE}) for c in ordered]) \
    - np.asarray([float(rows[c]["_difficulty"]) for c in ordered])
med = float(np.median(r0)); sig = 1.4826 * float(np.median(np.abs(r0 - med)))
kept = [c for c, ok in zip(ordered, np.abs(r0 - med) <= TRIM * sig) if ok]
TRAIN = [(c, float(rows[c]["_difficulty"])) for c in kept
         if rows[c]["nps_peak"] <= 1000 and rows[c]["chord_max"] <= 1000]
TRAIN += [(c, float(v)) for c, v in table.items()
          if c in rows and rows[c]["nps_peak"] <= 1000 and rows[c]["chord_max"] <= 1000]
print(f"training charts: {len(TRAIN)}  (trim sigma {sig:.2f})")


def clip_of(names):
    cl = {n: (min(float(rows[c][n]) for c, _ in TRAIN), max(float(rows[c][n]) for c, _ in TRAIN))
          for n in names if n in FEATS_ALL}
    # same evidence-based density ceilings fit_difficulty2 applies: beyond ~50/s the
    # labels stop rising, so an uncapped window density only lets burst charts explode
    if "nps_peak" in cl:
        cl["nps_peak"] = (cl["nps_peak"][0], min(cl["nps_peak"][1], 50.0))
    if "chord_max" in cl:
        cl["chord_max"] = (cl["chord_max"][0], min(cl["chord_max"][1], 12.0))
    for n in ("seg_nps_p50", "seg_nps_p90", "seg_nps_max"):
        if n in cl:
            cl[n] = (cl[n][0], min(cl[n][1], 50.0))
    return cl


def cv(names, clip, seeds=SEEDS):
    s = [(vfeat(c), y) for c, y in TRAIN]
    sc = []
    for seed in seeds:
        idx = np.random.default_rng(seed).permutation(len(s))
        ch = np.array_split(idx, 5)
        for k in range(5):
            tr = [s[i] for j in range(5) if j != k for i in ch[j]]
            te = [s[i] for i in ch[k]]
            m = fit_difficulty_model(tr, alpha=ALPHA, names=names, clip=clip, hinges=HINGES)
            p = np.asarray([m.predict_features(f) for f, _ in te])
            y = np.asarray([d for _, d in te])
            ss = float(((y - y.mean()) ** 2).sum())
            if ss > 0:
                sc.append(1 - float(((p - y) ** 2).sum()) / ss)
    return float(np.mean(sc))


def fit(names, clip):
    return fit_difficulty_model(
        [(vfeat(c), y) for c, y in TRAIN],
        alpha=ALPHA, names=names, clip=clip, hinges=HINGES)


print(f"\n{'variant':22} {'CV R2':>7}   " + "".join(f"#{c:<6}" for c in WATCH))
base_cv = cv(BASE_NAMES, clip_of(BASE_NAMES))
m = fit(BASE_NAMES, clip_of(BASE_NAMES))
print(f"{'baseline (17)':22} {base_cv:7.3f}   " + "".join(
    f"{m.predict_features(vfeat(c)):6.2f} " for c in WATCH))

adopted = []
for cand in CAND:
    names = BASE_NAMES + adopted + [cand]
    v = cv(names, clip_of(names))
    mm = fit(names, clip_of(names))
    flag = "  <-- improves" if v > base_cv + 1e-4 else ""
    print(f"{'+ ' + cand:22} {v:7.3f}{flag}   " + "".join(
        f"{mm.predict_features(vfeat(c)):6.2f} " for c in WATCH))
    if v > base_cv + 1e-4:
        adopted.append(cand)
        base_cv = v
print(f"\nadopted by forward selection: {adopted}")
if adopted:
    names = BASE_NAMES + adopted
    mm = fit(names, clip_of(names))
    pred = np.asarray([mm.predict_features(vfeat(c)) for c, _ in TRAIN])
    y = np.asarray([d for _, d in TRAIN])
    print(f"final CV R2={cv(names, clip_of(names)):.3f}  in-sample "
          f"R2={1 - ((pred - y) ** 2).sum() / ((y - y.mean()) ** 2).sum():.3f} "
          f"RMSE={np.sqrt(((pred - y) ** 2).mean()):.3f}")
