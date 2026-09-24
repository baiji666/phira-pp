"""Ground the hold weighting in real data.

Phira holds have no tail judgement, so a hold's per-key difficulty should drop —
and a very short hold (tap-and-lift) should sit just below a tap.  This measures
the actual hold-duration distribution (to pick a defensible "short" threshold)
and the note-type breakdown of the charts the user flagged.
"""

from __future__ import annotations

import glob
from pathlib import Path

import numpy as np

from phira_pp.loader import load_package
from phira_pp.models import NoteType

FLAGGED = (54540, 50333, 30942, 52597, 22206, 53994, 73474)
rows = []
for path in sorted(Path("data/packages").glob("*.bin")):
    cid = int(path.stem)
    try:
        chart = load_package(path.read_bytes())
    except Exception:  # noqa: BLE001
        continue
    notes = chart.playable_notes
    if not notes:
        continue
    holds = np.asarray([n.hold for n in notes if n.type == NoteType.HOLD])
    types = np.asarray([int(n.type) for n in notes])
    rows.append({
        "id": cid,
        "n": len(notes),
        "taps": int((types == NoteType.TAP).sum()),
        "holds": int((types == NoteType.HOLD).sum()),
        "flicks": int((types == NoteType.FLICK).sum()),
        "drags": int((types == NoteType.DRAG).sum()),
        "hold_secs": holds,
    })

all_holds = np.concatenate([r["hold_secs"] for r in rows if r["hold_secs"].size])
print(f"charts parsed: {len(rows)}   total hold notes: {all_holds.size}")
print("hold duration percentiles (s):")
for p in (1, 5, 10, 20, 25, 30, 40, 50, 60, 75, 90, 99):
    print(f"  p{p:<3d} {np.percentile(all_holds, p):7.3f}")
print(f"  min {all_holds.min():.4f}  max {all_holds.max():.2f}")

print("\nshare of holds below a threshold:")
for thr in (0.05, 0.08, 0.1, 0.12, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5):
    print(f"  < {thr:.2f}s : {float((all_holds < thr).mean()) * 100:5.1f}%")

print("\nper-chart share of notes that are short holds (thr=0.15s):")
shares = []
for r in rows:
    if r["n"]:
        shares.append(float((r["hold_secs"] < 0.15).sum()) / r["n"])
shares = np.asarray(shares)
print(f"  mean {shares.mean() * 100:.1f}%  p50 {np.percentile(shares, 50) * 100:.1f}%  "
      f"p90 {np.percentile(shares, 90) * 100:.1f}%  max {shares.max() * 100:.1f}%")

by_id = {r["id"]: r for r in rows}
print("\nflagged charts, note-type breakdown:")
print(f"{'id':>8} {'notes':>7} {'tap':>7} {'hold':>7} {'short':>7} {'flick':>7} {'drag':>7}  "
      f"{'hold_p50':>9}")
for cid in FLAGGED:
    r = by_id.get(cid)
    if not r:
        print(f"{cid:>8}  (not cached)")
        continue
    hs = r["hold_secs"]
    short = int((hs < 0.15).sum()) if hs.size else 0
    print(f"{cid:>8} {r['n']:>7} {r['taps']:>7} {r['holds']:>7} {short:>7} "
          f"{r['flicks']:>7} {r['drags']:>7}  {np.median(hs) if hs.size else 0:9.3f}")
