"""Are chords / drags inflating D*?  (`log_notes` counts every key equally.)

The flagged overestimates are all chord-heavy or drag-heavy: #54540 is 92% drags
with 10000 keys, #50333/#30942/#52597 have multi_frac 0.52-0.64, while the
underestimates have multi_frac 0.44-0.46.  Tests interaction terms built from the
cached columns, so no re-extraction is needed yet.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import numpy as np

from phira_pp.difficulty import cross_val_r2, fit_difficulty_model
from phira_pp.features import FEATURE_NAMES

ALPHAS = (3.0, 10.0, 30.0, 100.0)
SEEDS = (0, 1, 2, 3, 4)
GAIN = 0.010
CLEAN = set(json.loads(Path("data/train_clean_ids.json").read_text("utf-8")))

CAND = {
    "drag_x_notes": lambda r: r["drag_frac"] * r["log_notes"],
    "multi_x_notes": lambda r: r["multi_frac"] * r["log_notes"],
    "hold_x_notes": lambda r: r["hold_frac"] * r["log_notes"],
    "flick_x_notes": lambda r: r["flick_frac"] * r["log_notes"],
    "chord_x_notes": lambda r: r["chord_mean"] * r["log_notes"],
    "aim_x_multi": lambda r: np.log1p(r["aim_mean"] * r["multi_frac"]),
    "chord_max_x_multi": lambda r: r["chord_max"] * r["multi_frac"],
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
print(f"baseline CV R2 = {cv0:.3f} @alpha={a0}")
print("\none-at-a-time:")
for cand in CAND:
    cv, a = mean_cv([cand])
    print(f"  +{cand:18s} CV R2={cv:.3f} ({cv - cv0:+.3f})")

cur, cv = [], cv0
print("\nforward selection:")
while True:
    trials = [(mean_cv(cur + [c]), c) for c in CAND if c not in cur]
    if not trials:
        break
    (tcv, ta), cand = max(trials)
    print(f"  best try {cand:18s} CV R2={tcv:.3f} ({tcv - cv:+.3f})")
    if tcv > cv + GAIN:
        cur.append(cand)
        cv = tcv
        print(f"  ADOPT {cand} -> CV R2={cv:.3f}")
    else:
        print("  stop")
        break
print(f"final extras: {cur}  CV R2={cv:.3f}")

if cur:
    from phira_pp.dataset import load_model

    old = load_model("data/difficulty_model.json")
    s = samples(cur)
    m = fit_difficulty_model(s, alpha=ta)
    by_id = {r["_id"]: r for r in rows}
    print("\n新旧 D* 对比（你标记的谱面）：")
    for cid in (54540, 50333, 30942, 52597, 22206, 53994, 73474):
        r = by_id.get(cid)
        if r:
            print(f"  #{cid:<7d} 谱师定数={r['_difficulty']:<6} D*旧={old.predict_features(r):5.2f} "
                  f"D*新={m.predict_features(r):5.2f}")
