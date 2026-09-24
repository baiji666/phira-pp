r"""Duration / "stamina" analysis for D* (was a user-reported hypothesis).

Claimed: long charts (8-9 min, e.g. #22206, #39209) are severely under-estimated
by D*.  Measured on the cached corpus (both charter and subjective-table labels):

  * residual (D* - label) vs log_duration: corr = +0.06  -> no systematic trend;
  * by duration bucket the LONGEST band is *over*-predicted, not under:
        log_dur [0.0,2.0)  n= 56  mean residual +0.95
        log_dur [2.0,2.3)  n=691  mean residual +0.15
        log_dur [2.3,2.5)  n=147  mean residual +0.34
        log_dur [2.5,2.9)  n= 72  mean residual +0.79
  * the two named charts already sit at the top of the model's range
    (#22206 D*=20.00, #39209 D*=19.84); what the UI showed (18.5x) was the
    subjective 定数表 value overriding D* (that table caps below 18.60).
  * a "length reward" is not an independent choice in a linear model: the fitted
    ``log_duration`` coefficient IS the data's answer and it is NEGATIVE
    (-0.63/σ).  Dropping the feature costs CV: 0.825 -> 0.768.

    $env:PYTHONPATH="."; .\.venv\Scripts\python.exe scripts/diag_length.py
"""

from __future__ import annotations

import glob
import json

import numpy as np

from phira_pp.dataset import load_model
from phira_pp.difficulty import fit_difficulty_model
from phira_pp.features import FEATURES_VERSION, FEATURE_NAMES

ALPHA = 30.0
TRIM = 2.5
DMIN = 1.0
BASE = [n for n in FEATURE_NAMES if n != "log_eff"] + ["log_notes"]
ALL = FEATURE_NAMES + ["log_notes"]


def load():
    rows = {}
    for p in glob.glob("data/features/*.json"):
        try:
            f = json.loads(open(p, encoding="utf-8").read())
        except Exception:  # noqa: BLE001
            continue
        if f.get("_version") != FEATURES_VERSION or not all(k in f for k in ALL):
            continue
        rows[int(p.split("\\")[-1].split("/")[-1].split(".")[0])] = f
    return rows


def main() -> int:
    rows = load()
    model = load_model("data/difficulty_model.json")
    table = {r["id"]: r["difficulty"] for r in
             json.loads(open("data/subjective_diff.json", encoding="utf-8").read())["rows"]}

    print("== named charts ==")
    for cid in (22206, 39209):
        f = rows.get(cid)
        if not f:
            continue
        d = model.predict_features({k: f[k] for k in FEATURE_NAMES})
        print(f"  #{cid} 时长={10 ** f['log_duration'] / 60:.2f}min  "
              f"谱师={f.get('_difficulty')} 主观表={table.get(cid)} D*={d:.2f}")

    print("\n== residual vs log_duration ==")
    xs, ys, ds = [], [], []
    for cid, f in rows.items():
        d = model.predict_features({k: f[k] for k in FEATURE_NAMES})
        labels = []
        if isinstance(f.get("_difficulty"), (int, float)):
            labels.append(f["_difficulty"])
        if cid in table:
            labels.append(table[cid])
        for y in labels:
            if isinstance(y, (int, float)) and y >= DMIN:
                xs.append(f["log_duration"]); ys.append(y); ds.append(d)
    xs, ys, ds = map(np.asarray, (xs, ys, ds))
    res = ds - ys
    print(f"  n={len(xs)}  corr(log_duration, residual) = {np.corrcoef(xs, res)[0, 1]:+.3f}")
    for lo, hi in ((0, 2.0), (2.0, 2.3), (2.3, 2.5), (2.5, 2.9)):
        m = (xs >= lo) & (xs < hi)
        if m.sum():
            print(f"  [{lo},{hi})  n={int(m.sum()):4d}  mean residual {res[m].mean():+.2f}")

    print("\n== is log_duration carrying signal? (production recipe) ==")
    ordered = [cid for cid, f in rows.items()
               if cid not in table and isinstance(f.get("_difficulty"), (int, float))
               and f["_difficulty"] >= DMIN]
    samples = [({n: float(rows[cid][n]) for n in BASE}, float(rows[cid]["_difficulty"]))
               for cid in ordered]
    ref = fit_difficulty_model(samples, alpha=ALPHA, names=BASE)
    r0 = np.asarray([ref.predict_features(f) for f, _ in samples]) - np.asarray([d for _, d in samples])
    med = float(np.median(r0)); sigma = 1.4826 * float(np.median(np.abs(r0 - med)))
    keep = np.abs(r0 - med) <= TRIM * sigma
    kept_ids = [cid for cid, ok in zip(ordered, keep) if ok]

    def sample_set(ids):
        out = []
        for cid in ids:
            r = rows[cid]
            if r["nps_peak"] > 1000 or r["chord_max"] > 1000:
                continue
            out.append(({n: float(r[n]) for n in FEATURE_NAMES}, float(r["_difficulty"])))
        for cid, v in table.items():
            r = rows.get(cid)
            if not r or r["nps_peak"] > 1000 or r["chord_max"] > 1000:
                continue
            out.append(({n: float(r[n]) for n in FEATURE_NAMES}, float(v)))
        return out

    def cv(data, names=None):
        sc = []
        for seed in (0, 1, 2, 3, 4):
            idx = np.random.default_rng(seed).permutation(len(data))
            chunks = np.array_split(idx, 5)
            for k in range(5):
                tr = [data[i] for j in range(5) if j != k for i in chunks[j]]
                te = [data[i] for i in chunks[k]]
                m = fit_difficulty_model(tr, alpha=ALPHA, names=names)
                p = np.asarray([m.predict_features(f) for f, _ in te])
                y = np.asarray([d for _, d in te])
                ss = float(((y - y.mean()) ** 2).sum())
                if ss > 0:
                    sc.append(1 - float(((p - y) ** 2).sum()) / ss)
        return float(np.mean(sc))

    data = sample_set(kept_ids)
    print(f"  n={len(data)}")
    print(f"  with log_duration    CV R2 = {cv(data):.3f}")
    print(f"  without log_duration CV R2 = "
          f"{cv(data, names=[n for n in FEATURE_NAMES if n != 'log_duration']):.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
