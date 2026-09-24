r"""Two independent problems on extreme charts, measured separately.

1. EXTRAPOLATION.  #54540's chord_max=7346 / nps_peak=7376 are 40-700x beyond
   anything in the corpus (chord_max max = 170), so z = +736 / +244 and D* = 40.5.
   Clipping every feature to the range observed in training removes this by
   construction, without touching any in-range chart (so CV is unchanged).
2. SATURATION.  log_eff (largest weight, small sigma) pins every huge-notes chart
   near 20 even though their own labels say ~18.6.  A hinge on log_eff lets the
   slope flatten past a point; CV says it helps.

    $env:PYTHONPATH="."; .\.venv\Scripts\python.exe scripts/exp_saturation.py
"""

from __future__ import annotations

import glob
import json

import numpy as np

from phira_pp.difficulty import fit_difficulty_model
from phira_pp.dataset import load_model
from phira_pp.features import FEATURES_VERSION, FEATURE_NAMES

ALPHA = 30.0
TRIM = 2.5
DMIN = 1.0
SEEDS = (0, 1, 2, 3, 4)
WATCH = (54540, 22206, 16380, 39209, 3007)
BASE = [n for n in FEATURE_NAMES if n != "log_eff"] + ["log_notes"]
ALL = FEATURE_NAMES + ["log_notes"]

rows = {}
for p in glob.glob("data/features/*.json"):
    try:
        f = json.loads(open(p, encoding="utf-8").read())
    except Exception:  # noqa: BLE001
        continue
    if f.get("_version") != FEATURES_VERSION or not all(k in f for k in ALL):
        continue
    if not isinstance(f.get("_difficulty"), (int, float)):
        continue
    rows[int(p.split("\\")[-1].split("/")[-1].split(".")[0])] = f

table = {r["id"]: r["difficulty"] for r in
         json.loads(open("data/subjective_diff.json", encoding="utf-8").read())["rows"]}

ordered = [c for c, f in rows.items() if c not in table and f["_difficulty"] >= DMIN]
ref = fit_difficulty_model([({n: float(rows[c][n]) for n in BASE}, float(rows[c]["_difficulty"]))
                            for c in ordered], alpha=ALPHA, names=BASE)
r0 = np.asarray([ref.predict_features({n: float(rows[c][n]) for n in BASE}) for c in ordered]) \
    - np.asarray([float(rows[c]["_difficulty"]) for c in ordered])
med = float(np.median(r0)); sigma = 1.4826 * float(np.median(np.abs(r0 - med)))
kept = [c for c, ok in zip(ordered, np.abs(r0 - med) <= TRIM * sigma) if ok]

TRAIN = []
for c in kept:
    f = rows[c]
    if f["nps_peak"] <= 1000 and f["chord_max"] <= 1000:
        TRAIN.append((c, float(f["_difficulty"])))
for cid, v in table.items():
    f = rows.get(cid)
    if f and f["nps_peak"] <= 1000 and f["chord_max"] <= 1000:
        TRAIN.append((cid, float(v)))
train_feats = [{n: float(rows[c][n]) for n in FEATURE_NAMES} for c, _ in TRAIN]
CLIP = {n: (min(f[n] for f in train_feats), max(f[n] for f in train_feats))
        for n in FEATURE_NAMES}
print(f"training charts: {len(TRAIN)}")
print("clip range for the blown-up features:",
      {n: (round(CLIP[n][0], 2), round(CLIP[n][1], 2))
       for n in ("log_eff", "nps_peak", "chord_max")})


CAP = None   # upper cap for log_eff, set per variant below


def feats(cid, hinge=None, clip=False, cap=None):
    f = {n: float(rows[cid][n]) for n in FEATURE_NAMES}
    if clip:
        f = {n: min(max(v, CLIP[n][0]), CLIP[n][1]) for n, v in f.items()}
    if cap is not None:
        f["log_eff"] = min(f["log_eff"], cap)
    if hinge is not None:
        f["le_hinge"] = max(0.0, f["log_eff"] - hinge)
    return f


def names_for(hinge=None):
    return list(FEATURE_NAMES) + (["le_hinge"] if hinge is not None else [])


def cv(hinge=None, clip=False, cap=None):
    names = names_for(hinge)
    s = [(feats(c, hinge, clip, cap), y) for c, y in TRAIN]
    sc = []
    for seed in SEEDS:
        idx = np.random.default_rng(seed).permutation(len(s))
        chunks = np.array_split(idx, 5)
        for k in range(5):
            tr = [s[i] for j in range(5) if j != k for i in chunks[j]]
            te = [s[i] for i in chunks[k]]
            m = fit_difficulty_model(tr, alpha=ALPHA, names=names)
            p = np.asarray([m.predict_features(f) for f, _ in te])
            y = np.asarray([d for _, d in te])
            ss = float(((y - y.mean()) ** 2).sum())
            if ss > 0:
                sc.append(1 - float(((p - y) ** 2).sum()) / ss)
    return float(np.mean(sc))


def refit(hinge=None, clip=False, cap=None):
    return fit_difficulty_model([(feats(c, hinge, clip, cap), y) for c, y in TRAIN],
                                alpha=ALPHA, names=names_for(hinge))


variants = [("base (16)", None, False, None),
            ("clip only", None, True, None)]
for c in (3.6, 3.7, 3.8, 3.9):
    variants.append((f"clip+cap {c}", None, True, c))
for h in (3.4, 3.5):
    variants.append((f"clip+hinge {h}", h, True, None))
print(f"\n{'variant':16} {'CV R2':>7}   " + "".join(f"#{c:<7}" for c in WATCH))
for name, h, cl, cp in variants:
    m = refit(h, cl, cp)
    print(f"{name:16} {cv(h, cl, cp):7.3f}   " + "".join(
        f"{m.predict_features(feats(c, h, cl, cp)):7.2f} " for c in WATCH))
print("(label flattening starts at log_eff ~3.4; see scripts/diag_length.py)")

# corpus-wide disturbance of the simplest candidate
old = load_model("data/difficulty_model.json")
for tag, h, cp in (("clip+cap 3.8", None, 3.8), ("clip+hinge 3.4", 3.4, None)):
    m = refit(h, True, cp)
    d = np.asarray([abs(m.predict_features(feats(cid, h, True, cp))
                        - old.predict_features({k: rows[cid][k] for k in FEATURE_NAMES}))
                    for cid in rows])
    oor = sum(1 for cid in rows
              if not (0 <= m.predict_features(feats(cid, h, True, cp)) <= 20))
    print(f"\n{tag} vs current: |dD*| mean={d.mean():.3f} median={np.median(d):.3f} "
          f"p95={np.percentile(d, 95):.3f} max={d.max():.3f};  out of [0,20]: {oor}")
