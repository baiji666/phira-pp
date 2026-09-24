r"""Verification for the subjective 定数表 integration (``data/subjective_diff.json``).

Reproduces, on real data, why the table is wired the way it is:

1. ``subjective_diff.json`` parses, every id is unique, and every 定数 respects the
   table's own cap ("不会对 18.60 及以上进行定数").
2. the merged chain (:func:`phira_pp.pipeline.load_tables`) resolves as required —
   Suonasi wins on overlap, the subjective value fills the gaps, and the ranked
   charter 定数 outranks both.
3. prints the ids the new table newly covers, with their D* side by side.

Usage:
    $env:PYTHONPATH="."; .\.venv\Scripts\python.exe scripts/verify_subjective.py
"""

from __future__ import annotations

import json
import statistics as st
import sys
from collections import Counter
from pathlib import Path

from phira_pp.pipeline import (
    OVERRIDE_SOURCE,
    SUBJECTIVE_FLOOR_SOURCE,
    PPEngine,
    load_tables,
)

ROOT = Path(__file__).resolve().parent.parent
SUBJECTIVE = ROOT / "data" / "subjective_diff.json"
KV = ROOT / "data" / "kv_diff.json"
CAP = 18.60
failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("  OK  " if cond else "  FAIL") + "  " + msg)
    if not cond:
        failures.append(msg)


def main() -> int:
    subj = json.loads(SUBJECTIVE.read_text("utf-8"))["rows"]
    kv_ids = {int(r["id"]) for r in json.loads(KV.read_text("utf-8"))["rows"]}
    sids = [r["id"] for r in subj]

    print("[1] source file")
    check(len(sids) == len(set(sids)), f"ids unique ({len(sids)} rows)")
    check(all(r["difficulty"] < CAP for r in subj),
          f"every 定数 < {CAP} (table's own cap)")
    check(all(isinstance(r["id"], int) for r in subj), "every row has a numeric chart id")

    print("[2] merged difficulty chain")
    tables = load_tables("data")
    src = Counter(s for _, s in tables.values())
    print("      ", dict(src), "total", len(tables))
    check(tables.get(322) == (19.0, "定数表 (Suonasi)"),
          "overlap #322 -> Suonasi value (主观 18.47 ignored)")
    gap = tables.get(4083)
    check(gap is not None and gap[1] == "定数表 (主观)",
          f"gap #4083 -> subjective value ({gap})")
    check(tables.get(22206) == (19.4, "专家覆盖 (override)"),
          "override #22206 -> expert value beats the subjective table")

    engine = PPEngine(cache_dir="data")
    meta = engine.client.get_chart(7516)
    d, s = engine.anchor_difficulty(7516, meta)
    check(s == "定数 (ranked)" and abs(d - 17.5) < 1e-3,
          f"ranked #7516 -> charter 定数 ({d:.4f}), outranks table value")

    for cid in (30942, 36301):
        meta = engine.client.get_chart(cid)
        d, s = engine.anchor_difficulty(cid, meta)
        check(s == SUBJECTIVE_FLOOR_SOURCE and d > tables.get(cid, (0, ""))[0],
              f"subjective floor: #{cid} {tables.get(cid, (0,''))[0]:.2f} -> {d:.2f} [{s}]")

    for cid, want in ((22206, 19.4), (39209, 19.6)):
        meta = engine.client.get_chart(cid)
        d, s = engine.anchor_difficulty(cid, meta)
        check(s == OVERRIDE_SOURCE and abs(d - want) < 1e-9,
              f"expert override: #{cid} -> {d:.2f} [{s}] (want {want})")

    print("[3] charts the new table newly covers (主观 not in Suonasi)")
    only = [r for r in subj if r["id"] not in kv_ids]
    rows, absent = [], []
    for r in sorted(only, key=lambda r: -r["difficulty"]):
        try:
            m = engine.client.get_chart(r["id"])
        except Exception:  # noqa: BLE001 - id absent from the API
            absent.append(r["id"])
            continue
        rows.append((r["id"], r["name"], r["difficulty"], engine.d_star(m)))

    print(f"       {len(only)} ids, {len(rows)} on the live API, "
          f"{len(absent)} absent (404, inert): {absent}")
    for cid, name, sd, d in rows:
        ds = "None" if d is None else f"{d:.2f}"
        print(f"       {cid:6} 主观={sd:5.2f}  D*={ds:>5}  {name[:34]}")
    pairs = [(sd, d) for _, _, sd, d in rows if d is not None]
    if pairs:
        print(f"       mean(主观-D*)={st.mean(a - b for a, b in pairs):+.2f}  "
              f"mean|diff|={st.mean(abs(a - b) for a, b in pairs):.2f}  "
              f"({len(pairs)} charts)")

    print()
    if failures:
        print(f"FAILED: {len(failures)} check(s)")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
