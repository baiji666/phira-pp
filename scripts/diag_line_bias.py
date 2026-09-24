"""Is D* biased against these two chart types?

  1. many judge-line changes (high line_speed_p90 / line_rot_p90),
  2. almost no line displacement but high density (statics / 纯物量).

Mean residual (pred - label) per stratum; a clearly positive value means the
model OVERestimates that group.  Run before changing anything.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import numpy as np

from phira_pp.dataset import load_model

model = load_model("data/difficulty_model.json")
clean_ids = set(json.loads(Path("data/train_clean_ids.json").read_text("utf-8")))

rows = []
for path in glob.glob("data/features/*.json"):
    cid = int(Path(path).stem)
    if cid not in clean_ids:
        continue
    f = json.loads(open(path, encoding="utf-8").read())
    if not all(k in f for k in model.names):
        continue
    f["_id"] = cid
    rows.append(f)

pred = np.asarray([model.predict_features(r) for r in rows])
y = np.asarray([r["_difficulty"] for r in rows])
res = pred - y
print(f"n={len(rows)}  mean resid={res.mean():+.3f}  RMSE={np.sqrt((res**2).mean()):.3f}")

ls = np.asarray([r["line_speed_p90"] for r in rows])
lr = np.asarray([r["line_rot_p90"] for r in rows])
hf = np.asarray([r["hidden_frac"] for r in rows])
nps = np.asarray([r["nps_peak"] for r in rows])
print(f"line_speed_p90: min={ls.min():.2f} p50={np.median(ls):.2f} p90={np.percentile(ls,90):.2f} max={ls.max():.2f}")
print(f"line_rot_p90  : min={lr.min():.2f} p50={np.median(lr):.2f} p90={np.percentile(lr,90):.2f} max={lr.max():.2f}")
print(f"hidden_frac   : p50={np.median(hf):.3f} p90={np.percentile(hf,90):.3f}")


def strata(name, values, qs=(0, 20, 40, 60, 80, 100)):
    edges = np.percentile(values, qs)
    edges[-1] += 1e-9
    print(f"\nmean residual by {name} quintile:")
    for i in range(len(edges) - 1):
        m = (values >= edges[i]) & (values < edges[i + 1])
        if m.sum():
            print(f"  [{edges[i]:8.2f},{edges[i+1]:8.2f})  n={m.sum():4d}  "
                  f"mean resid={res[m].mean():+6.3f}  mean |resid|={np.abs(res[m]).mean():5.3f}")


strata("line_speed_p90", ls)
strata("line_rot_p90", lr)

print("\nstatic line (line_speed below median) x density:")
med_ls, med_nps = np.median(ls), np.median(nps)
for lo_hi in ((True, True), (True, False), (False, True), (False, False)):
    static, dense = lo_hi
    m = ((ls <= med_ls) if static else (ls > med_ls)) & \
        ((nps >= med_nps) if dense else (nps < med_nps))
    tag = ("静态线" if static else "移动线") + " + " + ("高密度" if dense else "低密度")
    if m.sum():
        print(f"  {tag:16s} n={m.sum():4d}  mean resid={res[m].mean():+6.3f}  "
              f"mean label={y[m].mean():5.2f}  mean pred={pred[m].mean():5.2f}")

# correlation of the line features with the residual itself
print("\ncorr(feature, residual):")
for name in ("line_speed_p90", "line_rot_p90", "hidden_frac", "nps_peak", "log_notes",
             "log_duration", "dt_cv", "aim_mean", "aim_p99", "dir_change_p80"):
    col = np.asarray([r[name] for r in rows])
    print(f"  {name:16s} {np.corrcoef(col, res)[0,1]:+.3f}")
