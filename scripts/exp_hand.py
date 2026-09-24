r"""Audit items 3 & 4: 4-finger reachability features, and the duration sign.

Item 4 (duration): the fitted ``log_duration`` weight is NEGATIVE because, with
total 物量 (``log_eff``) already in the model, duration acts as the inverse of
density -- "same work spread over longer = easier".  The project owner requires
the opposite ("时长越长应该越难"), and the reference scheme sidesteps it by not
using duration at all.  Tested here: keep (fitted, negative) / drop / and a
FIXED POSITIVE stamina coefficient ``lam`` (a policy parameter, since a fitted
sign cannot be forced).

Item 3 (reachability): the reference spends 23.6% of its splits on G5/G9 hand
features.  Ours: ``hand_step_p95`` / ``hand_speed_p95`` / ``hand_overreach_frac``
from a 4-finger nearest-neighbour assignment (see features._hand_stats).

    $env:PYTHONPATH="."; .\.venv\Scripts\python.exe scripts/exp_hand.py
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
NAMES = FEATURE_NAMES + [HINGE_NAME]
HINGES = {HINGE_NAME: ("log_eff", LE_HINGE)}
HAND = ["hand_step_p95", "hand_speed_p95", "hand_overreach_frac"]
CAPS = {"nps_peak": 50.0, "chord_max": 12.0, "seg_nps_p90": 50.0}
BASE = [n for n in FEATURE_NAMES if n != "log_eff"] + ["log_notes"]
ALL = FEATURE_NAMES + [c for c in CANDIDATE_FEATURES if c not in FEATURE_NAMES] + ["log_notes"]
WATCH = (22206, 39209, 54540, 3007, 31028)


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
print(f"cached charts: {len(rows)}")

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
print(f"training charts: {len(TRAIN)}")

MU_DUR = float(np.mean([rows[c]["log_duration"] for c, _ in TRAIN]))
SD_DUR = float(np.std([rows[c]["log_duration"] for c, _ in TRAIN]))


def vfeat(c):
    return {n: float(rows[c][n]) for n in FEATURE_NAMES + HAND}


def clip_of(names):
    cl = {n: (min(float(rows[c][n]) for c, _ in TRAIN), max(float(rows[c][n]) for c, _ in TRAIN))
          for n in names if n in FEATURE_NAMES + HAND}
    for k, cap in CAPS.items():
        if k in cl:
            cl[k] = (cl[k][0], min(cl[k][1], cap))
    return cl


def fit(names, clip, lam=None, drop_dur=False):
    """``lam`` = fixed positive stamina coefficient; ``drop_dur`` = no duration at all."""
    ns = [n for n in names if not (drop_dur and n == "log_duration")]
    data = []
    for c, y in TRAIN:
        y2 = y if lam is None else y - lam * (rows[c]["log_duration"] - MU_DUR) / SD_DUR
        data.append((vfeat(c), y2))
    return fit_difficulty_model(data, alpha=ALPHA, names=ns, clip=clip, hinges=HINGES), ns


def predict(m, c, lam):
    v = m.predict_features(vfeat(c))
    return v + (0.0 if lam is None else lam * (rows[c]["log_duration"] - MU_DUR) / SD_DUR)


def cv(names, clip, lam=None, drop_dur=False, seeds=SEEDS):
    ns = [n for n in names if not (drop_dur and n == "log_duration")]
    sc = []
    for seed in seeds:
        idx = np.random.default_rng(seed).permutation(len(TRAIN))
        ch = np.array_split(idx, 5)
        for k in range(5):
            tr = [TRAIN[i] for j in range(5) if j != k for i in ch[j]]
            te = [TRAIN[i] for i in ch[k]]
            data = []
            for c, y in tr:
                y2 = y if lam is None else y - lam * (rows[c]["log_duration"] - MU_DUR) / SD_DUR
                data.append((vfeat(c), y2))
            m = fit_difficulty_model(data, alpha=ALPHA, names=ns, clip=clip, hinges=HINGES)
            p = np.asarray([predict(m, c, lam) for c, _ in te])
            y = np.asarray([v for _, v in te])
            ss = float(((y - y.mean()) ** 2).sum())
            if ss > 0:
                sc.append(1 - float(((p - y) ** 2).sum()) / ss)
    return float(np.mean(sc))


def show(tag, names, var):
    m, _ = fit(names, clip_of(names), **var)
    print(f"{tag:26} {cv(names, clip_of(names), **var):7.3f}   " + "".join(
        f"{predict(m, c, var.get('lam')):6.2f} " for c in WATCH))


print(f"\n{'variant':26} {'CV R2':>7}   " + "".join(f"#{c:<6}" for c in WATCH))
show("baseline (18)", NAMES, {})
for h in HAND:
    show(f"+ {h}", NAMES + [h], {})

best = NAMES + ["hand_step_p95"]
print(f"\n-- duration handling (with hand_step_p95) --")
show("keep (fitted, negative)", best, {})
show("drop duration", best, {"drop_dur": True})
for lam in (0.1, 0.2, 0.3):
    show(f"stamina lam={lam}", best, {"drop_dur": True, "lam": lam})
