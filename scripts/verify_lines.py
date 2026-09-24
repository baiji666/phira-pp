"""Verify the RPE line-event implementation against real cached charts.

Checks (all on real data, no assumptions):
  * evaluated line positions stay inside the documented ranges (-675..675,
    -450..450) for the vast majority of sampled times;
  * note on-screen positions (line pos + note offset) stay inside playfield
    bounds;
  * how often ``bpmfactor != 1`` (a documented ambiguity) and how often
    ``bezier == 1`` (unsupported by the reference implementation) occur.
"""

import collections
import glob
import json
import zipfile

import numpy as np

from phira_pp.beats import parse_beat
from phira_pp.lineevents import RpeLineSet

SAMPLES = 120


def main():
    files = sorted(glob.glob("data/packages/*.bin"))
    out_x = in_x = 0
    out_y = in_y = 0
    max_xs, max_ys = [], []
    note_out = 0
    note_total = 0
    bpmfactor_bad = 0
    lines_with_bpmfactor = 0
    bezier_events = 0
    total_events = 0
    charts = 0
    pair_total = 0
    pair_excl = 0

    for path in files:
        try:
            with zipfile.ZipFile(path) as zf:
                members = [n for n in zf.namelist() if n.lower().endswith(".json")]
                if not members:
                    continue
                data = json.loads(zf.read(members[0]))
        except Exception:  # noqa: BLE001
            continue
        if not (isinstance(data, dict) and ("META" in data or "BPMList" in data)):
            continue
        charts += 1

        lines_raw = data.get("judgeLineList", [])
        for ln in lines_raw:
            bf = float(ln.get("bpmfactor", 1.0))
            lines_with_bpmfactor += 1
            if abs(bf - 1.0) > 1e-9:
                bpmfactor_bad += 1
            for layer in (ln.get("eventLayers") or []):
                if not layer:
                    continue
                for key, evs in layer.items():
                    if not isinstance(evs, list):
                        continue
                    for e in evs:
                        total_events += 1
                        if int(e.get("bezier", 0)) == 1:
                            bezier_events += 1

        lines = RpeLineSet(lines_raw)

        # sample beat range from all notes
        beats = []
        for ln in lines_raw:
            for n in ln.get("notes", []):
                beats.append(parse_beat(n["startTime"]))
        if not beats:
            continue
        lo, hi = min(beats), max(beats)
        if hi <= lo:
            hi = lo + 1.0
        sample_beats = np.linspace(lo, hi, SAMPLES)

        chart_max_x = chart_max_y = 0.0
        for i in range(len(lines)):
            for b in sample_beats:
                x, y = lines.pos(i, float(b))
                if abs(x) > 675:
                    out_x += 1
                else:
                    in_x += 1
                if abs(y) > 450:
                    out_y += 1
                else:
                    in_y += 1
                chart_max_x = max(chart_max_x, abs(x))
                chart_max_y = max(chart_max_y, abs(y))
        max_xs.append(chart_max_x)
        max_ys.append(chart_max_y)

        # note on-screen bounds (translation only)
        for i, ln in enumerate(lines_raw):
            for n in ln.get("notes", []):
                b = parse_beat(n["startTime"])
                x, y = lines.pos(i, b)
                wx = x + float(n.get("positionX", 0.0))
                wy = y
                note_total += 1
                if abs(wx) > 900 or abs(wy) > 700:
                    note_out += 1

        # on-screen gate exclusion rate over consecutive note pairs
        seq = []
        for i, ln in enumerate(lines_raw):
            for n in ln.get("notes", []):
                if int(n.get("isFake", 0)) == 1:
                    continue
                b = parse_beat(n["startTime"])
                x, y = lines.pos(i, b)
                seq.append((b, abs(x) <= 675 and abs(y) <= 450))
        seq.sort()
        prev = None
        for _, on in seq:
            if prev is not None:
                pair_total += 1
                if not (on and prev):
                    pair_excl += 1
            prev = on

    print(f"RPE charts scanned: {charts}")
    print(f"line-position samples: |x|<=675 {in_x/(in_x+out_x):.4f}   |y|<=450 {in_y/(in_y+out_y):.4f}")
    mx = np.asarray(max_xs)
    my = np.asarray(max_ys)
    print(f"per-chart max |x|: mean={mx.mean():.1f} p95={np.percentile(mx,95):.1f} max={mx.max():.1f}")
    print(f"per-chart max |y|: mean={my.mean():.1f} p95={np.percentile(my,95):.1f} max={my.max():.1f}")
    print(f"note on-screen out-of-bounds (|wx|>900 or |wy|>700): {note_out}/{note_total} "
          f"= {note_out/max(1,note_total):.5f}")
    print(f"lines with bpmfactor != 1: {bpmfactor_bad}/{lines_with_bpmfactor}")
    print(f"bezier==1 events: {bezier_events}/{total_events} "
          f"= {bezier_events/max(1,total_events):.5f}")
    print(f"consecutive note pairs excluded by on-screen gate: {pair_excl}/{pair_total} "
          f"= {pair_excl/max(1,pair_total):.5f}")


if __name__ == "__main__":
    main()
