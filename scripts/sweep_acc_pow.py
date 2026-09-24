"""Sweep acc_pow (the accuracy curve steepness) with diff_exp fixed.

Reports, per acc_pow: the Best-100 span, the accuracy-factor curve, and how many
hardness inversions (harder chart, >=1.0 定数, still scores less) appear.
"""

import dataclasses

from phira_pp.pipeline import PPEngine
from phira_pp.pp import performance_pp

USER = 459003
eng = PPEngine()
res, _ = eng.best_plays_direct(USER)
data = [(p.difficulty, p.record) for p in res
        if p.difficulty is not None and p.breakdown is not None]
print(f"plays: {len(data)}  diff_exp={eng.params.diff_exp}\n")


def rows_for(pow_):
    params = dataclasses.replace(eng.params, acc_pow=pow_)
    rows = [(performance_pp(d, r, params).pp, d, r.accuracy) for d, r in data]
    rows.sort(key=lambda x: -x[0])
    return rows


def af(acc, pow_, floor=0.70):
    return 0.0 if acc < floor else ((acc - floor) / (1 - floor)) ** pow_


print("acc_factor 曲线:")
print(f"{'acc':>6} " + "".join(f"{'p=' + str(p):>9}" for p in (2.0, 3.0, 4.0, 5.0)))
for acc in (1.0, 0.995, 0.99, 0.98, 0.97, 0.95, 0.93):
    print(f"{acc * 100:>5.1f}% " + "".join(f"{af(acc, p):>9.4f}" for p in (2.0, 3.0, 4.0, 5.0)))

print()
hdr = (f"{'pow':>4} {'gap':>7} {'#1':>8} {'#100':>8} {'b1/b100':>8} {'total100':>9} "
       f"{'inv':>4} {'min定数 top100':>13}")
print(hdr)
print("-" * len(hdr))
for p in (2.0, 3.0, 4.0, 5.0):
    rows = rows_for(p)
    top = rows[:100]
    total = sum(x * (0.95 ** i) for i, (x, _d, _a) in enumerate(top))
    inv = sum(1 for a in rows for b in rows
              if b[1] - a[1] >= 1.0 and a[2] >= 0.999 and b[2] >= 0.9950 and a[0] > b[0])
    print(f"{p:>4.1f} {top[0][0] - top[-1][0]:>7.1f} {top[0][0]:>8.1f} {top[-1][0]:>8.1f} "
          f"{top[0][0] / top[-1][0]:>8.3f} {total:>9.1f} {inv:>4d} "
          f"{min(x[1] for x in top):>13.2f}")

print()
for p in (2.0, 4.0):
    rows = rows_for(p)
    top = rows[:100]
    print(f"acc_pow={p} 示例:")
    for tag, i in (("#1", 0), ("#50", 49), ("#100", 99)):
        x, d, a = top[i]
        print(f"    {tag:>4} pp={x:>7.1f}  定数={d:>5.2f}  acc={a * 100:>6.2f}%")
