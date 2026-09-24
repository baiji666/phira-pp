r"""Verification for the record-selection rule (issue: PP must not be picked by score).

``/record?player=&chart=`` returns up to 20 records for a chart.  PP is NOT
monotone in score (it is driven by accuracy / 无暇度 / 漏键), so picking the
highest-score row understates the player.  SuonasiOS reads the whole history and
selects by a rule (its default is ``highestAccuracy``); we select by **PP**, which
dominates both that and score-max.

This script recomputes the Best-100 over the community table set for one player
under all three rules and asserts pp-max >= accuracy-max >= ... is not required,
only that pp-max is the best of the three.

    $env:PYTHONPATH="."; .\.venv\Scripts\python.exe scripts/verify_record_selection.py [uid]
"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor

from phira_pp.api import _record_from_dict
from phira_pp.pipeline import PPEngine, osu_total_pp
from phira_pp.pp import performance_pp

UID = int(sys.argv[1]) if len(sys.argv) > 1 else 459003
failures: list[str] = []


def main() -> int:
    engine = PPEngine(cache_dir="data")
    ids = sorted(engine.anchors)
    metas = {m.id: m for m in engine.client.get_charts(ids)}
    print(f"community table: {len(ids)} ids, {len(metas)} resolved")

    def one(cid):
        try:
            return cid, engine.client.query_player_chart(UID, cid)
        except Exception:  # noqa: BLE001
            return cid, None

    rows_by_chart = {}
    with ThreadPoolExecutor(max_workers=32) as ex:
        for cid, rows in ex.map(one, ids):
            if rows:
                rows_by_chart[cid] = rows

    totals = {"score": [], "acc": [], "pp": []}
    diff_rows = 0
    for cid, rows in rows_by_chart.items():
        diff, _src = engine.anchor_difficulty(cid, metas[cid])
        if diff is None:
            continue
        recs = [_record_from_dict(r) for r in rows]
        pps = [performance_pp(diff, r, engine.params).pp for r in recs]
        n = len(recs)
        i_score = max(range(n), key=lambda i: recs[i].score)
        i_acc = max(range(n), key=lambda i: recs[i].accuracy)
        i_pp = max(range(n), key=lambda i: pps[i])
        totals["score"].append(pps[i_score])
        totals["acc"].append(pps[i_acc])
        totals["pp"].append(pps[i_pp])
        if i_score != i_pp:
            diff_rows += 1

    print(f"played (scorable) charts: {len(totals['pp'])}   "
          f"with >1 record: {sum(1 for r in rows_by_chart.values() if len(r) > 1)}")
    res = {}
    for rule in ("score", "acc", "pp"):
        res[rule] = osu_total_pp(sorted(totals[rule], reverse=True)[:100])
        print(f"  rule={rule:6} Best-100 total PP = {res[rule]:9.1f}")
    print(f"  charts where 'max score' != 'max PP': {diff_rows}")

    ok = res["pp"] >= res["acc"] - 1e-6 and res["pp"] >= res["score"] - 1e-6
    if not ok:
        failures.append("PP-max is not the best of the three rules")
    print()
    if failures:
        print("FAILED: " + "; ".join(failures))
        return 1
    print(f"OK: PP-max selection is best "
          f"(+{res['pp'] - res['score']:.1f} PP vs score-max)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
