"""Where does the Best-100 compression come from?

Prints, for several diff_exp, the pp and (定数, acc) of #1/#50/#100 so it is
visible whether the tightness is driven by difficulty or by accuracy.
"""

import dataclasses

from phira_pp.pipeline import PPEngine
from phira_pp.pp import performance_pp

USER = 459003
eng = PPEngine()
res, _ = eng.best_plays_direct(USER)
data = [(p.difficulty, p.record) for p in res
        if p.difficulty is not None and p.breakdown is not None]
print(f"plays: {len(data)}\n")


def rows_for(de):
    params = dataclasses.replace(eng.params, diff_exp=de)
    rows = [(performance_pp(d, r, params).pp, d, r.accuracy, r) for d, r in data]
    rows.sort(key=lambda x: -x[0])
    return rows


for de in (2.0, 4.0, 6.0, 8.0):
    rows = rows_for(de)
    top = rows[:100]
    total = sum(p * (0.95 ** i) for i, (p, *_ ) in enumerate(top))
    inv = sum(1 for a in rows for b in rows
              if b[1] - a[1] >= 1.0 and a[2] >= 0.999 and b[2] >= 0.9950 and a[0] > b[0])
    print(f"=== diff_exp={de}: gap={top[0][0] - top[-1][0]:.1f} "
          f"ratio={top[0][0] / top[-1][0]:.3f} total100={total:.1f} inv={inv} "
          f"定数span={min(x[1] for x in top):.2f}~{max(x[1] for x in top):.2f} "
          f"lowest-diff-in-top100={min(x[1] for x in top):.2f}")
    for tag, i in (("#1", 0), ("#50", 49), ("#100", 99)):
        p, d, a, _r = top[i]
        print(f"    {tag:>4} pp={p:>7.1f}  定数={d:>5.2f}  acc={a * 100:>6.2f}%")
    print()

# 参照：同等准确度下难度曲线本身（acc=100%、无漏键、std 不计）
print("理论(acc=100%):")
for de in (2.0, 4.0, 6.0, 8.0):
    params = dataclasses.replace(eng.params, diff_exp=de)
    f = lambda d: params.base * d ** de
    print(f"    exp={de}: D17={f(17.0):.0f} D18={f(18.0):.0f} D19.3={f(19.3):.0f} "
          f"19.3/17.0={f(19.3) / f(17.0):.3f}")
