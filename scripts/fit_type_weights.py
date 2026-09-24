"""Fit note-type 物量 weights, constrained by the expert ordering
``long_hold > tap > short_hold > flick > drag``.

Rationale from the user (domain expert): Phira holds have NO tail judgement, so a
hold occupies a finger but judges like a tap; a very short hold (tap-and-lift)
should sit slightly *below* a tap.  The weights themselves are then fitted by CV
against the cleaned charter labels — only the ORDER is taken from expert
judgement, no hand-picked magnitudes.

Short-hold threshold: 0.15 s, which is ~p40 of the measured hold-duration
distribution (175,394 holds over 975 charts) and below a quarter-beat at typical
BPMs; sensitivity to 0.10 / 0.20 is reported.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import numpy as np

from phira_pp.difficulty import cross_val_r2, fit_difficulty_model
from phira_pp.features import FEATURE_NAMES
from phira_pp.loader import load_package
from phira_pp.models import NoteType

ALPHAS = (3.0, 10.0, 30.0, 100.0)
SEEDS = (0, 1, 2, 3, 4)
CLEAN = set(json.loads(Path("data/train_clean_ids.json").read_text("utf-8")))
FLAGGED = (54540, 50333, 30942, 52597, 22206, 53994, 73474)
GRID_LONG = (1.0, 1.10, 1.25)
GRID_SHORT = (0.65, 0.75, 0.85, 0.95)
GRID_FLICK = (0.45, 0.60, 0.75)
GRID_DRAG = (0.20, 0.35, 0.50)


def counts_of(cid: int, short_thr: float) -> dict | None:
    path = Path("data/packages") / f"{cid}.bin"
    if not path.exists():
        return None
    try:
        notes = load_package(path.read_bytes()).playable_notes
    except Exception:  # noqa: BLE001
        return None
    out = {"tap": 0, "long": 0, "short": 0, "flick": 0, "drag": 0}
    for n in notes:
        if n.type == NoteType.TAP:
            out["tap"] += 1
        elif n.type == NoteType.HOLD:
            out["long" if n.hold >= short_thr else "short"] += 1
        elif n.type == NoteType.FLICK:
            out["flick"] += 1
        elif n.type == NoteType.DRAG:
            out["drag"] += 1
    return out


def load_cases(short_thr: float):
    rows, counts = [], {}
    for path in glob.glob("data/features/*.json"):
        cid = int(Path(path).stem)
        if cid not in CLEAN:
            continue
        f = json.loads(open(path, encoding="utf-8").read())
        if not all(k in f for k in FEATURE_NAMES):
            continue
        c = counts_of(cid, short_thr)
        if c is None:
            continue
        f["_id"] = cid
        rows.append(f)
        counts[cid] = c
    return rows, counts


def eff(c: dict, w_long: float, w_short: float, w_flick: float, w_drag: float) -> float:
    return (c["tap"] + w_long * c["long"] + w_short * c["short"]
            + w_flick * c["flick"] + w_drag * c["drag"])


def evaluate(rows, counts, w, short_thr, replace=True):
    names = [n for n in FEATURE_NAMES if not (replace and n == "log_notes")] + ["log_eff"]
    samples = []
    for r in rows:
        feats = {n: float(r[n]) for n in FEATURE_NAMES if not (replace and n == "log_notes")}
        feats["log_eff"] = float(np.log10(max(1.0, eff(counts[r["_id"]], *w))))
        samples.append((feats, float(r["_difficulty"])))
    best, alpha = -9.9, None
    for a in ALPHAS:
        v = float(np.mean([cross_val_r2(samples, alpha=a, names=names, seed=s) for s in SEEDS]))
        if v > best:
            best, alpha = v, a
    return best, alpha


for thr in (0.15,):
    rows, counts = load_cases(thr)
    print(f"short-hold threshold {thr}s: usable {len(rows)} charts")
    base = [n for n in FEATURE_NAMES if n != "log_notes"] + ["log_notes"]
    b_samples = [({**{n: float(r[n]) for n in FEATURE_NAMES}}, float(r["_difficulty"])) for r in rows]
    b_best, b_alpha = -9.9, None
    for a in ALPHAS:
        v = float(np.mean([cross_val_r2(b_samples, alpha=a, names=base, seed=s) for s in SEEDS]))
        if v > b_best:
            b_best, b_alpha = v, a
    print(f"baseline (raw log_notes) CV R2 = {b_best:.3f} @alpha={b_alpha}")

    results = []
    for w_long in GRID_LONG:
        for w_short in GRID_SHORT:
            for w_flick in GRID_FLICK:
                for w_drag in GRID_DRAG:
                    if not (w_short > w_flick > w_drag):
                        continue
                    cv, a = evaluate(rows, counts,
                                     (w_long, w_short, w_flick, w_drag), thr)
                    results.append((cv, a, (w_long, w_short, w_flick, w_drag)))
    results.sort(reverse=True)
    print("\ntop 8 weight sets (1.0 = tap):")
    for cv, a, w in results[:8]:
        print(f"  long={w[0]:.2f} short={w[1]:.2f} flick={w[2]:.2f} drag={w[3]:.2f} "
              f"-> CV R2={cv:.3f} ({cv - b_best:+.3f}) @alpha={a}")

    cv, a, w = results[0]
    print(f"\nbest = {w}   CV R2={cv:.3f} ({cv - b_best:+.3f})")
    names = [n for n in FEATURE_NAMES if n != "log_notes"] + ["log_eff"]
    samples = []
    for r in rows:
        feats = {n: float(r[n]) for n in FEATURE_NAMES if n != "log_notes"}
        feats["log_eff"] = float(np.log10(max(1.0, eff(counts[r["_id"]], *w))))
        samples.append((feats, float(r["_difficulty"])))
    model = fit_difficulty_model(samples, alpha=a, names=names)
    from phira_pp.dataset import load_model
    old = load_model("data/difficulty_model.json")
    print("\n你标记的 7 张：加权后 D* 是否朝你说的方向移动？")
    print(f"{'id':>8} {'谱师':>6} {'D*旧':>7} {'D*新':>7}  你的判断")
    verdict = {54540: "高估", 50333: "高估", 30942: "高估", 52597: "高估",
               22206: "低估", 53994: "低估", 73474: "稍有高估"}
    for cid in FLAGGED:
        r = next((x for x in rows if x["_id"] == cid), None)
        if r is None:
            print(f"{cid:>8}  (不在清洗后的训练集里)")
            continue
        f_new = {n: float(r[n]) for n in FEATURE_NAMES if n != "log_notes"}
        f_new["log_eff"] = float(np.log10(max(1.0, eff(counts[cid], *w))))
        print(f"{cid:>8} {r['_difficulty']:>6} {old.predict_features(r):>7.2f} "
              f"{model.predict_features(f_new):>7.2f}  {verdict[cid]}")
