"""Sweep PP policy params: how many ordering inversions remain?

An "inversion": chart B is >=1.0 定数 harder and its accuracy is >=99.5%, yet it
still scores less PP than an easier chart A whose accuracy is >=99.9%.

Records are fetched once; only the PP params vary.
"""

import dataclasses
import itertools

from phira_pp.pipeline import PPEngine
from phira_pp.pp import performance_pp

USER = 0
eng = PPEngine()
res, _ = eng.best_plays_direct(USER)

data = [(p.difficulty, p.record) for p in res
        if p.difficulty is not None and p.breakdown is not None]
print("plays used:", len(data))

ERROR_MAX = 0.996  # worst plausible 漏键 multiplier at these accuracies


def inversions(params):
    rows = []
    for d, rec in data:
        b = performance_pp(d, rec, params)
        rows.append((b.pp, d, rec.accuracy, b.precision_factor))
    n = 0
    worst = None
    for a in rows:                       # a easier/higher-acc, b harder
        for b in rows:
            if b[1] - a[1] >= 1.0 and a[2] >= 0.999 and b[2] >= 0.9950 and a[0] > b[0]:
                n += 1
                margin = b[0] / a[0]
                if worst is None or margin < worst[0]:
                    worst = (margin, a, b)
    return n, worst


print(f"{'diff_exp':>8} {'prec_w':>7} {'inversions':>11}   worst B/A margin")
for de, pw in itertools.product([2.0, 2.5, 3.0], [0.20, 0.15, 0.10, 0.08, 0.05]):
    params = dataclasses.replace(eng.params, diff_exp=de, precision_weight=pw)
    n, worst = inversions(params)
    w = f"{worst[0]:.4f} ({worst[1][1]:.2f}->{worst[2][1]:.2f})" if worst else "-"
    print(f"{de:>8.1f} {pw:>7.2f} {n:>11d}   {w}")

print("\nCurrent setting:", {k: getattr(eng.params, k) for k in
                             ("diff_exp", "precision_weight", "precision_lo", "precision_hi")})
