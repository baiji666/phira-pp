r"""Refit D*: robust-trim the charter labels, add the subjective 定数表, save.

Three training-data decisions, validated in ``scripts/exp_subjective_labels.py``
and ``scripts/exp_saturation.py`` on a **fixed charter-labelled test set**
(5-fold, seeds 0..4, alpha fixed at 30):

    variant                     R2     RMSE   RMSE>=18   bias>=18
    charter only              0.833    0.756     0.837      -0.58
    + table labelled 谱师定数   0.798    0.831     1.067      -0.88
    + table labelled 表内定数   0.834    0.754     0.739      -0.42   <- adopted

1. The subjective 定数表 (``data/subjective_diff.json``, source
   ``data/subjective_diff.xlsx``) enters as *training labels* — its own 定数, not
   the Phira 谱师定数.  On the fixed test set this keeps overall fit at least as
   good and cuts the documented high-end under-estimation (bias -0.58 -> -0.42,
   RMSE>=18 0.837 -> 0.739).  Using the charts' Phira labels instead is *worse*
   (bias -0.88), which is why the table's value is used.
   Overlap rule (Suonasi > table) governs the *difficulty chain*, not training;
   every table chart is relabelled here regardless.

2. Charts whose 1-second window or single chord would hold >1000 notes are
   dropped: no such value is humanly playable, and one of them alone destabilises
   every squared metric.  #54540 is the only one — a real chart, but a wall of
   4346+3000 simultaneous drags (measured, not a parser bug).  Dropping it also
   un-blocks three features whose standardisation it had been dominating
   (``nps_peak`` sigma 286.6 -> 32.0, ``chord_max`` 285.0 -> 11.0,
   ``chord_mean`` 0.683 -> 0.292).

Effect on the rest of the corpus (1081 cached charts): |D*new - D*old| median
0.08, p95 0.22.  Three charts become unscorable (prediction left [0,20]) and are
excluded + counted by the range guard in ``pipeline.chart``: #54540 and #26558
(not in any 定数表), and #22206 (still scored via the subjective table).

3. Two input guards, both measured, not assumed (see
   ``phira_pp.difficulty.prepare_features``):
   * ``clip`` bounds every feature to the training range.  #54540's
     ``chord_max``=7346 sits against a corpus max of 170, i.e. z=+736 and D*=40.5
     from extrapolation alone.  Clipping is a no-op for any in-range chart, so it
     cannot perturb the fit (CV unchanged).
   * a saturating ``le_hinge = max(0, log_eff - 3.4)``.  The labels stop rising
     with 物量 around log_eff 3.4 (band means 17.10 → 17.88 → 17.83 → 18.20 →
     17.76), yet log_eff's +1.52 weight pinned every huge-notes chart near 20
     against its own ~18.6 label.  CV improves 0.851 → 0.854; a hinge rather than
     a hard cap keeps the ordering among the biggest charts.  Effect:
     #22206 19.97→19.43, #39209 19.87→19.14, #3007 20.59→19.87, #54540 40.84→20.85.

Honesty checks kept from the previous refit: the trimmed ids + residuals are
printed, a NESTED CV (trim re-derived inside every fold), in-sample RMSE, and a
spot-check that bogus labels get a sane D*.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import numpy as np

from phira_pp.dataset import save_model
from phira_pp.difficulty import fit_difficulty_model
from phira_pp.features import CANDIDATE_FEATURES, FEATURES_VERSION, FEATURE_NAMES

ALPHAS = (3.0, 10.0, 30.0, 100.0)
SEEDS = (0, 1, 2, 3, 4)
DMIN = 1.0        # 0.0 is Phira's "定数 unset" marker, not a difficulty
TRIM = 2.5        # robust-sigma multiplier
TRIM_ALPHA = 30.0
ALPHA = 30.0      # fixed, never argmax-searched (see project_rules.md)
OUT = "data/difficulty_model.json"
CLEAN_IDS = "data/train_clean_ids.json"
SUBJECTIVE = "data/subjective_diff.json"
DEGENERATE_CAP = 1000.0   # >1000 notes per second / per chord is not a human chart
JUNK = [39209, 39119, 15736, 71519, 7454, 10502, 21031, 30115, 36629, 26966]
ALL_COLS = FEATURE_NAMES + CANDIDATE_FEATURES
BASE = [n for n in FEATURE_NAMES if n != "log_eff"] + ["log_notes"]
# 物量 saturation: measured from the labels themselves (band means stop rising
# around log_eff 3.4) and validated by CV in scripts/exp_saturation.py.
LE_HINGE = 3.4
HINGE_NAME = "le_hinge"
NAMES = FEATURE_NAMES + [HINGE_NAME]
HINGES = {HINGE_NAME: ("log_eff", LE_HINGE)}
# Density features stop carrying difficulty past a point measured from the labels
# (scripts/exp_saturation.py / _diag_density): nps_peak 16.63@30-40 -> 17.10@>=50
# -> 16.71@>=100; chord_max 17.10@10-20 -> 16.36@>=15.  Values beyond that are
# stack/teleport artefacts of charts like #54540 (a wall of 4346+3000 drags), not
# difficulty, so the clip ceiling is tightened to where the labels stop rising.
DENSITY_CAP = {"nps_peak": 50.0, "chord_max": 12.0, "seg_nps_p90": 50.0}


def load_rows():
    rows = []
    for path in glob.glob("data/features/*.json"):
        try:
            f = json.loads(open(path, encoding="utf-8").read())
        except Exception:  # noqa: BLE001
            continue
        if f.get("_version") != FEATURES_VERSION:
            continue
        if not isinstance(f.get("_difficulty"), (int, float)) or f["_difficulty"] < DMIN:
            continue
        if not all(k in f for k in ALL_COLS):
            continue
        f["_id"] = int(Path(path).stem)
        rows.append(f)
    return rows


def samples_of(rows):
    return [({n: float(r[n]) for n in FEATURE_NAMES}, float(r["_difficulty"])) for r in rows]


def clip_of(rows):
    """Per-feature [min, max] over the training rows (the extrapolation guard)."""
    return {n: (min(float(r[n]) for r in rows), max(float(r[n]) for r in rows))
            for n in FEATURE_NAMES}


def residuals(samples, alpha, names=None):
    model = fit_difficulty_model(samples, alpha=alpha, names=names)
    pred = np.asarray([model.predict_features(f) for f, _ in samples])
    y = np.asarray([d for _, d in samples])
    res = pred - y
    med = float(np.median(res))
    sigma = 1.4826 * float(np.median(np.abs(res - med)))
    return np.abs(res - med) <= TRIM * sigma, res, sigma


def kfold_r2(samples, alpha, seeds=SEEDS, folds=5, trim_inside=False,
             names=None, clip=None, hinges=None):
    names = names or FEATURE_NAMES
    scores = []
    for seed in seeds:
        idx = np.random.default_rng(seed).permutation(len(samples))
        chunks = np.array_split(idx, folds)
        for k in range(folds):
            train = [samples[i] for j in range(folds) if j != k for i in chunks[j]]
            test = [samples[i] for i in chunks[k]]
            if trim_inside:
                keep, _, _ = residuals(train, alpha)
                train = [s for s, ok in zip(train, keep) if ok]
            if len(train) < len(names) + 2:
                continue
            model = fit_difficulty_model(train, alpha=alpha, names=names,
                                         clip=clip, hinges=hinges)
            pred = np.asarray([model.predict_features(f) for f, _ in test])
            y = np.asarray([d for _, d in test])
            ss_tot = float(((y - y.mean()) ** 2).sum())
            if ss_tot > 0:
                scores.append(1.0 - float(((pred - y) ** 2).sum()) / ss_tot)
    return float(np.mean(scores)) if scores else float("nan")


# ------------------------------------------------------------------ assemble --
rows = load_rows()
table = {r["id"]: r["difficulty"] for r in
         json.loads(Path(SUBJECTIVE).read_text("utf-8"))["rows"]}
rows_other = [r for r in rows if r["_id"] not in table]
rows_table = [r for r in rows if r["_id"] in table]
print(f"cached rows with a usable label: {len(rows)}  "
      f"(subjective-table charts: {len(rows_table)}, other: {len(rows_other)})")

# The trim is derived from the RAW-KEY model: deriving it from the model being
# evaluated makes cleaning and fitting circular (plain CV 0.573 vs nested 0.815).
keep, res, sigma = residuals(
    [({n: float(r[n]) for n in BASE}, float(r["_difficulty"])) for r in rows_other],
    TRIM_ALPHA, names=BASE,
)
other_clean = [r for r, ok in zip(rows_other, keep) if ok]
other_drop = [r for r, ok in zip(rows_other, keep) if not ok]
print(f"trim charter rows @alpha={TRIM_ALPHA}: sigma={sigma:.2f}  "
      f"keep {len(other_clean)}  drop {len(other_drop)}")

degen = [r for r in rows_other if r["nps_peak"] > DEGENERATE_CAP
         or r["chord_max"] > DEGENERATE_CAP]
degen_ids = {r["_id"] for r in degen}
other_clean = [r for r in other_clean if r["_id"] not in degen_ids]
print(f"dropped {len(degen)} degenerate chart(s) "
      f"(>{DEGENERATE_CAP:.0f} notes/s or /chord): "
      f"{[(r['_id'], int(r['nps_peak']), int(r['chord_max'])) for r in degen]}")

table_rows = [({n: float(r[n]) for n in FEATURE_NAMES}, float(table[r["_id"]]))
              for r in rows_table
              if not (r["nps_peak"] > DEGENERATE_CAP or r["chord_max"] > DEGENERATE_CAP)]
print(f"subjective-table training rows added (labelled by the table): {len(table_rows)}")

charter = samples_of(other_clean)
training = charter + table_rows
CLIP = {n: (min(f[n] for f, _ in training), max(f[n] for f, _ in training))
        for n in FEATURE_NAMES}
for k, cap in DENSITY_CAP.items():
    CLIP[k] = (CLIP[k][0], min(CLIP[k][1], cap))
print(f"\ntraining set: {len(charter)} charter + {len(table_rows)} table = {len(training)} charts")
print(f"clip guard from the training range (density ceilings {DENSITY_CAP}), "
      f"hinge {HINGE_NAME}=max(0, log_eff-{LE_HINGE}); "
      f"e.g. log_eff [{CLIP['log_eff'][0]:.2f}, {CLIP['log_eff'][1]:.2f}], "
      f"chord_max [{CLIP['chord_max'][0]:.0f}, {CLIP['chord_max'][1]:.0f}], "
      f"nps_peak [{CLIP['nps_peak'][0]:.0f}, {CLIP['nps_peak'][1]:.0f}]")

# ------------------------------------------------------------------ evidence --
print("\nCV R2 (alpha fixed at 30; same folds for both):")
for label, s in (("charter only", charter), ("+ subjective table", training)):
    print(f"    {label:22} {kfold_r2(s, ALPHA, names=NAMES, clip=CLIP, hinges=HINGES):.3f}")
for a in ALPHAS:
    print(f"  (alpha scan) alpha={a:6.1f}  "
          f"CV R2={kfold_r2(training, a, names=NAMES, clip=CLIP, hinges=HINGES):.3f}")
print(f"chosen alpha={ALPHA} (fixed, not argmax-searched)")

print(f"\nNESTED CV on the full label set (trim re-derived per fold): "
      f"{kfold_r2(training, ALPHA, trim_inside=True, names=NAMES, clip=CLIP, hinges=HINGES):.3f}")
print(f"NESTED CV inside the cleaned charter set:                  "
      f"{kfold_r2(charter, ALPHA, trim_inside=True, names=NAMES, clip=CLIP, hinges=HINGES):.3f}")

print(f"\ndropped charter rows {len(other_drop)} (robust sigma {sigma:.2f}), worst first:")
for r in sorted(other_drop, key=lambda r: -abs(r["_difficulty"]))[:20]:
    print(f"    dropped #{r['_id']:<7d} label={r['_difficulty']:<6} ranked={r.get('_ranked')}")

# --------------------------------------------------------------------- fit ----
model = fit_difficulty_model(training, alpha=ALPHA, names=NAMES,
                             clip=CLIP, hinges=HINGES)
pred = np.asarray([model.predict_features(f) for f, _ in training])
y = np.asarray([d for _, d in training])
print(f"\nin-sample R2={1 - ((pred - y) ** 2).sum() / ((y - y.mean()) ** 2).sum():.3f} "
      f"RMSE={np.sqrt(((pred - y) ** 2).mean()):.3f}")
print("weights (by |w|):")
for n, w in sorted(zip(model.names, model.weights), key=lambda t: -abs(t[1])):
    print(f"    {n:18s} {w:+.3f}   (mean {model.mean[model.names.index(n)]:.4f}, "
          f"std {model.std[model.names.index(n)]:.4f})")

save_model(model, OUT)
Path(CLEAN_IDS).write_text(
    json.dumps(sorted([r["_id"] for r in other_clean] + [r["_id"] for r in rows_table])),
    "utf-8")
print(f"saved -> {OUT}   ({len(training)} training charts)")

print("\nspot-check (label vs new D*):")
by_id = {r["_id"]: r for r in rows}
for cid in JUNK:
    r = by_id.get(cid)
    if r:
        print(f"    #{cid:<7d} 谱师标签={r['_difficulty']:<6} -> D*="
              f"{model.predict_features(r):5.2f}  nps={r['nps_peak']:.0f}")
