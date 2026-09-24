"""Who exactly does D* overestimate?  List the worst offenders with names.

This is the direct check on "judge-line-heavy charts are overrated": if the
biggest positive residuals are dominated by high line_speed_p90 / high
line_rot_p90 charts, the claim holds for the worst cases (even if the group mean
is flat).  Also lists the worst UNDERestimates as a control.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import numpy as np

from phira_pp.api import PhiraClient
from phira_pp.dataset import load_model
from phira_pp.features import FEATURE_NAMES

model = load_model("data/difficulty_model.json")
clean = set(json.loads(Path("data/train_clean_ids.json").read_text("utf-8")))

rows = []
for path in glob.glob("data/features/*.json"):
    cid = int(Path(path).stem)
    if cid not in clean:
        continue
    f = json.loads(open(path, encoding="utf-8").read())
    if not all(k in f for k in FEATURE_NAMES):
        continue
    f["_id"] = cid
    rows.append(f)

pred = np.asarray([model.predict_features(r) for r in rows])
y = np.asarray([r["_difficulty"] for r in rows])
res = pred - y
order = np.argsort(-res)
ls = np.asarray([r["line_speed_p90"] for r in rows])
lr = np.asarray([r["line_rot_p90"] for r in rows])
nps = np.asarray([r["nps_peak"] for r in rows])
hf = np.asarray([r["hidden_frac"] for r in rows])
nn = np.asarray([r["_note_count"] for r in rows])

ids = [rows[i]["_id"] for i in order[:18]] + [rows[i]["_id"] for i in order[-18:]]
names = {}
try:
    names = {m.id: m.name for m in PhiraClient().get_charts(ids)}
except Exception as exc:  # noqa: BLE001
    print("name lookup failed:", exc)


def show(title, idxs):
    print(f"\n=== {title} ===")
    print(f"{'id':>8} {'label':>6} {'D*':>6} {'resid':>6} {'lineSpd':>8} {'lineRot':>9} "
          f"{'nps':>6} {'hide':>5} {'notes':>6}  name")
    for i in idxs:
        print(f"{rows[i]['_id']:>8} {y[i]:6.1f} {pred[i]:6.2f} {res[i]:+6.2f} "
              f"{ls[i]:8.2f} {lr[i]:9.1f} {nps[i]:6.1f} {hf[i]:5.2f} {nn[i]:6d}  "
              f"{names.get(rows[i]['_id'], '?')[:30]}")


show("D* OVERestimates most", order[:18])
show("D* UNDERestimates most", order[-18:])

print("\nwithin the top-18 overestimates:")
print(f"  line_speed_p90 >= p90 of all: {int((ls[order[:18]] >= np.percentile(ls, 90)).sum())}/18")
print(f"  line_rot_p90   >= p90 of all: {int((lr[order[:18]] >= np.percentile(lr, 90)).sum())}/18")
print(f"  line_speed_p90 <= p20 of all: {int((ls[order[:18]] <= np.percentile(ls, 20)).sum())}/18")
print(f"  mean line_speed: over={ls[order[:18]].mean():.2f}  all={ls.mean():.2f}")
print(f"  mean nps_peak  : over={nps[order[:18]].mean():.1f}  all={nps.mean():.1f}")
