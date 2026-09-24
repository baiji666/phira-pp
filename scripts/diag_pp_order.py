"""Diagnose PP ordering: does an easier chart at 100% outrank a harder one?

Dumps every played chart with its PP factors and reports "inversions" where a
chart that is >=1.0 定数 easier (with a higher accuracy) still scores more PP.
"""

import sys

from phira_pp.pipeline import PPEngine

USER = int(sys.argv[1]) if len(sys.argv) > 1 else 459003

eng = PPEngine()
res, stats = eng.best_plays_direct(USER)
print("stats:", stats, "->", len(res), "plays")
print()

rows = []
for p in res:
    b = p.breakdown
    if b is None or p.difficulty is None:
        continue
    r = p.record
    rows.append(dict(
        cid=p.chart.id, name=p.chart.name, src=p.difficulty_source, diff=p.difficulty,
        acc=r.accuracy, std=r.std, bad=r.bad, miss=r.miss, total=r.total_judged,
        pp=b.pp, af=b.acc_factor, pf=b.precision_factor, ef=b.error_factor,
    ))
rows.sort(key=lambda x: -x["pp"])

hdr = f"{'#':>3} {'pp':>8} {'定数':>6} {'acc%':>7} {'std_ms':>7} {'acc_f':>6} {'prec_f':>6} {'err_f':>6} {'来源':<18} name"
print(hdr)
print("-" * len(hdr))
for i, x in enumerate(rows[:30], 1):
    print(f"{i:>3} {x['pp']:>8.1f} {x['diff']:>6.2f} {x['acc'] * 100:>7.3f} "
          f"{x['std'] * 1000:>7.2f} {x['af']:>6.3f} {x['pf']:>6.3f} {x['ef']:>6.3f} "
          f"{x['src']:<18} {x['name'][:26]}")

inv = []
for a in rows:                       # a = lower 定数, higher acc, yet higher pp
    for b in rows:
        if b["diff"] - a["diff"] >= 1.0 and a["acc"] >= 0.999 and b["acc"] >= 0.9950:
            if a["pp"] > b["pp"]:
                inv.append((a, b))
print(f"\ninversions (easier>=+1.0 定数, higher acc, still more pp): {len(inv)}")
for a, b in inv[:8]:
    gap = b["diff"] - a["diff"]
    diff_ratio = (b["diff"] / a["diff"]) ** eng.params.diff_exp
    print(f"  A #{a['cid']} {a['diff']:.2f}@{a['acc'] * 100:.2f}% pp={a['pp']:.1f} (prec {a['pf']:.3f})"
          f"  vs  B #{b['cid']} {b['diff']:.2f}@{b['acc'] * 100:.2f}% pp={b['pp']:.1f} (prec {b['pf']:.3f})")
    print(f"      +{gap:.2f} 定数 -> D^e x{diff_ratio:.4f};  "
          f"B/A acc x{b['af'] / a['af']:.4f}, prec x{b['pf'] / a['pf']:.4f}, err x{b['ef'] / a['ef']:.4f}; "
          f"B/A pp x{b['pp'] / a['pp']:.4f}")
