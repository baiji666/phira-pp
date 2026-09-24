"""Does counting ONSETS / per-type 物量 instead of raw keys fix D*?

A 4-key chord is one press and a drag is not a tap, but ``log_notes`` counts every
key equally — which is what inflated the charts the user flagged.  Tests the
decomposition with the usual CV protocol (no hand-picked type weights: the fit
learns them).
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import numpy as np

from phira_pp.dataset import load_model
from phira_pp.difficulty import cross_val_r2, fit_difficulty_model
from phira_pp.features import FEATURE_NAMES

ALPHAS = (3.0, 10.0, 30.0, 100.0)
SEEDS = (0, 1, 2, 3, 4)
GAIN = 0.010
CLEAN = set(json.loads(Path("data/train_clean_ids.json").read_text("utf-8")))
FLAGGED = (54540, 50333, 30942, 52597, 22206, 53994, 73474)

ADD = {
    "log_onsets": lambda r: r["log_onsets"],
    "log_taps": lambda r: r["log_taps"],
    "log_drags": lambda r: r["log_drags"],
    "log_holds": lambda r: r["log_holds"],
    "log_flicks": lambda r: r["log_flicks"],
}
# name -> replacement columns built from a row
REPLACE = {
    "onsets_only": lambda r: {"log_onsets": r["log_onsets"]},
    "types_only": lambda r: {"log_taps": r["log_taps"], "log_holds": r["log_holds"],
                             "log_flicks": r["log_flicks"], "log_drags": r["log_drags"]},
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


def build(drop=(), add=(), repl=None):
    names = [n for n in FEATURE_NAMES if n not in drop]
    out = []
    for r in rows:
        feats = {n: float(r[n]) for n in names}
        if repl:
            feats.update({k: float(v) for k, v in repl(r).items()})
        for a in add:
            feats[a] = float(ADD[a](r))
        out.append((feats, float(r["_difficulty"])))
    return out, names + (list(repl(rows[0]).keys()) if repl else []) + list(add)


def mean_cv(drop=(), add=(), repl=None):
    s, names = build(drop, add, repl)
    best, alpha = -9.9, None
    for a in ALPHAS:
        v = float(np.mean([cross_val_r2(s, alpha=a, names=names, seed=sd) for sd in SEEDS]))
        if v > best:
            best, alpha = v, a
    return best, alpha


cv0, a0 = mean_cv()
print(f"baseline CV R2 = {cv0:.3f} @alpha={a0}")

print("\nadd one:")
for a in ADD:
    cv, _ = mean_cv(add=[a])
    print(f"  +{a:12s} {cv:.3f} ({cv - cv0:+.3f})")

print("\nreplace log_notes:")
opts = []
for label, fn in REPLACE.items():
    cv, _ = mean_cv(drop=("log_notes",), repl=fn)
    print(f"  {label:12s} {cv:.3f} ({cv - cv0:+.3f})")
    opts.append((cv, label, fn))
opts.sort(reverse=True)

print("\nforward selection:")
cur_drop, cur_add, cur_rep = (), [], None
cv = cv0
for _ in range(4):
    trials = []
    for a in ADD:
        if a not in cur_add:
            tcv, ta = mean_cv(cur_drop, cur_add + [a], cur_rep)
            trials.append((tcv, ta, "add", a))
    for label, fn in REPLACE.items():
        if cur_rep is None:
            tcv, ta = mean_cv(("log_notes",), cur_add, fn)
            trials.append((tcv, ta, "rep", (label, fn)))
    if not trials:
        break
    tcv, ta, kind, payload = max(trials)
    name = payload if kind == "add" else payload[0]
    print(f"  best try {name:14s} CV R2={tcv:.3f} ({tcv - cv:+.3f})")
    if tcv > cv + GAIN:
        if kind == "add":
            cur_add.append(payload)
        else:
            cur_drop = ("log_notes",)
            cur_rep = payload[1]
        cv = tcv
        print(f"  ADOPT {name} -> CV R2={cv:.3f} @alpha={ta}")
    else:
        print("  stop")
        break

final_add = cur_add
final_rep = cur_rep
print(f"\nfinal: drop={cur_drop} add={final_add} replace={list(REPLACE)[0] if final_rep else None}  CV R2={cv:.3f}")

if cv > cv0 + GAIN:
    s, names = build(cur_drop, final_add, final_rep)
    m = fit_difficulty_model(s, alpha=ta)
    old = load_model("data/difficulty_model.json")
    by_id = {r["_id"]: r for r in rows}
    print("\n新旧 D* 对比（你标记的谱面；label = 谱师定数）：")
    for cid in FLAGGED:
        r = by_id.get(cid)
        if r:
            print(f"  #{cid:<7d} label={r['_difficulty']:<6} D*旧={old.predict_features(r):5.2f} "
                  f"D*新={m.predict_features(r):5.2f}")
    print("\n新模型权重（按 |w|）:")
    for n, w in sorted(zip(names, m.weights), key=lambda t: -abs(t[1]))[:10]:
        print(f"    {n:16s} {w:+.3f}")
