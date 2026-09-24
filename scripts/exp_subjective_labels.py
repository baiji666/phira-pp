r"""Does the subjective 定数表 improve D*?

D* is canonically scored against the Phira **谱师定数** (the cache's
``_difficulty``).  The honest question is therefore: *holding the test set fixed
at trustworthy charter-labelled charts, does adding the subjective table to the
training data improve prediction of charter 定数?*

Protocol
  * pool   = cached charts with a numeric label and no membership in the table
  * EVAL   = that pool after the standard RAW-KEY robust trim  (labels trustworthy)
  * folds  = 5-fold, seeds 0..4, identical across variants; the charter part of
    each training fold is re-trimmed inside-fold (the two 铁律 in project_rules.md)
  * ALPHA  = 30, fixed

Variants
  T0  charter cache only                          (baseline)
  T1  + the table's charts labelled by 谱师定数     (isolates "just more data")
  T2  + the table's charts labelled by the table   (the proposal)

Metrics are reported twice: on everything, and excluding the *degenerate* charts
(a 1-second window or a single chord cannot hold >1000 notes; such feature values
are parser/nonsense artefacts and one of them alone swamps a squared metric).

    $env:PYTHONPATH="."; .\.venv\Scripts\python.exe scripts/exp_subjective_labels.py
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import numpy as np

from phira_pp.difficulty import fit_difficulty_model
from phira_pp.features import FEATURES_VERSION, FEATURE_NAMES

ROOT = Path(__file__).resolve().parent.parent
ALPHA = 30.0
SEEDS = (0, 1, 2, 3, 4)
FOLDS = 5
TRIM = 2.5
DMIN = 1.0
DEGENERATE_CAP = 1000.0   # >1000 notes per second / per chord is not a human chart
BASE = [n for n in FEATURE_NAMES if n != "log_eff"] + ["log_notes"]
ALL = FEATURE_NAMES + ["log_notes"]


def load_cache() -> tuple[dict[int, dict], int]:
    cache, skipped = {}, 0
    for path in glob.glob(str(ROOT / "data" / "features" / "*.json")):
        try:
            f = json.loads(open(path, encoding="utf-8").read())
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(f.get("_difficulty"), (int, float)) or f.get("_version") != FEATURES_VERSION:
            skipped += 1
            continue
        if not all(k in f for k in ALL):
            skipped += 1
            continue
        cache[int(Path(path).stem)] = f
    return cache, skipped


def full_of(f: dict) -> dict:
    return {n: float(f[n]) for n in ALL}


def pick(full: dict, names) -> dict:
    return {n: full[n] for n in names}


def trimmed(items):
    """Robust-trim against the RAW-KEY reference model (never the evaluated one)."""
    ref = [(pick(full, BASE), y) for full, y, _ in items]
    model = fit_difficulty_model(ref, alpha=ALPHA, names=BASE)
    res = np.asarray([model.predict_features(f) for f, _ in ref]) - np.asarray([d for _, d in ref])
    med = float(np.median(res))
    sigma = 1.4826 * float(np.median(np.abs(res - med)))
    return [it for it, ok in zip(items, np.abs(res - med) <= TRIM * sigma) if ok]


def r2(pred, y) -> float:
    ss = float(((y - y.mean()) ** 2).sum())
    return float("nan") if ss <= 0 else 1.0 - float(((pred - y) ** 2).sum()) / ss


def main() -> int:
    cache, skipped = load_cache()
    doc = json.loads((ROOT / "data" / "subjective_diff.json").read_text("utf-8"))
    table = {r["id"]: r["difficulty"] for r in doc["rows"]}
    names = {r["id"]: r["name"] for r in doc["rows"]}
    print(f"labelled cache rows: {len(cache)}   skipped (unlabelled/wrong-version/incomplete): {skipped}")

    subj_ids = sorted(i for i in table if i in cache)
    print(f"table ids with features: {len(subj_ids)}/{len(table)}   "
          f"without: {sorted(set(table) - set(cache))}")

    pool = [(full_of(cache[i]), float(cache[i]["_difficulty"]), i)
            for i in cache if i not in table and float(cache[i]["_difficulty"]) >= DMIN]
    eval_items = trimmed(pool)

    degenerate = {cid for full, _, cid in eval_items
                  if full["nps_peak"] > DEGENERATE_CAP or full["chord_max"] > DEGENERATE_CAP}
    # production also drops such charts from TRAINING (fit_difficulty2.py); mirror it
    degen_train = {cid for cid, f in cache.items()
                   if f["nps_peak"] > DEGENERATE_CAP or f["chord_max"] > DEGENERATE_CAP}
    print(f"pool {len(pool)} -> trimmed EVAL {len(eval_items)}")
    print(f"degenerate in EVAL (> {DEGENERATE_CAP:.0f} notes/s or /chord): "
          f"{sorted(degenerate)}  "
          f"{[(c, names.get(c, '')) for c in sorted(degenerate)]}")
    for cid in sorted(degen_train):
        f = cache[cid]
        print(f"    #{cid} nps_peak={f['nps_peak']:.0f} chord_max={f['chord_max']:.0f} "
              f"label={f['_difficulty']:.2f}  (excluded from training)")
    print()

    t1_pool = [(full_of(cache[i]), float(cache[i]["_difficulty"]), i) for i in subj_ids]
    # table labels are a curated reference, so they are never robust-trimmed
    t2_pool = [(full_of(cache[i]), float(table[i]), i) for i in subj_ids]
    variants = {"T0 charter-only": None, "T1 +table.charter": t1_pool, "T2 +table.table": t2_pool}

    print(f"{'variant':24} {'R2 all':>7} {'RMSE':>7} {'medAE':>7} "
          f"{'R2 >=18':>8} {'RMSE >=18':>10} {'bias >=18':>10}")
    for name, extra in variants.items():
        for skip_name, skip in (("", set()), ("excl-degenerate", degenerate)):
            P, Y = [], []
            for seed in SEEDS:
                idx = np.random.default_rng(seed).permutation(len(eval_items))
                chunks = np.array_split(idx, FOLDS)
                for k in range(FOLDS):
                    tr = [eval_items[i] for j in range(FOLDS) if j != k for i in chunks[j]]
                    te = [eval_items[i] for i in chunks[k]]
                    tr = trimmed(tr)
                    tr = [it for it in tr if it[2] not in degen_train]
                    if extra:
                        tr = tr + extra
                    model = fit_difficulty_model(
                        [(pick(f, FEATURE_NAMES), y) for f, y, _ in tr], alpha=ALPHA)
                    for f, y, cid in te:
                        if cid in skip:
                            continue
                        P.append(model.predict_features(pick(f, FEATURE_NAMES)))
                        Y.append(y)
            pred, y = np.asarray(P), np.asarray(Y)
            m = y >= 18.0
            tag = f"{name}{' [!]' if skip_name else ''}"
            print(f"{tag:24} {r2(pred, y):7.3f} "
                  f"{np.sqrt(((pred - y) ** 2).mean()):7.3f} "
                  f"{np.median(np.abs(pred - y)):7.3f} {r2(pred[m], y[m]):8.3f} "
                  f"{np.sqrt(((pred[m] - y[m]) ** 2).mean()):10.3f} "
                  f"{(pred[m] - y[m]).mean():+10.2f}")

    print("\nfull-data refit (all trimmed pool + extra), D* on the charts you flagged:")
    models = {}
    for name, extra in variants.items():
        tr = [it for it in trimmed(pool) if it[2] not in degen_train] + (extra or [])
        models[name] = fit_difficulty_model(
            [(pick(f, FEATURE_NAMES), y) for f, y, _ in tr], alpha=ALPHA)
    print(f"  {'id':>6} {'charter':>8} {'D* T0':>7} {'D* T1':>7} {'D* T2':>7}  name")
    for cid in (54540, 50333, 30942, 52597, 22206, 53994, 73474):
        if cid not in cache:
            print(f"  {cid:6} (no cached features)")
            continue
        full = full_of(cache[cid])
        v = [models[k].predict_features(pick(full, FEATURE_NAMES)) for k in variants]
        print(f"  {cid:6} {cache[cid]['_difficulty']:8.2f} "
              f"{v[0]:7.2f} {v[1]:7.2f} {v[2]:7.2f}  {names.get(cid, '')[:26]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
