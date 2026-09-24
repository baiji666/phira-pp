"""Measure how much RPE event-layer composition could possibly matter.

For each line and each position-relevant property (moveX/moveY/rotate) we count
how many layers define that property, and — when >=2 do — what fraction of time
more than one layer has an active event.  If that overlap is negligible, the
(undocumented) layer-composition rule cannot affect the result.
"""

import collections
import glob
import io
import json
import zipfile

import numpy as np

PROPS = ("moveXEvents", "moveYEvents", "rotateEvents")
SAMPLES = 200


def beat_value(b):
    if isinstance(b, (int, float)):
        return float(b)
    if isinstance(b, (list, tuple)):
        a = float(b[0]) if len(b) > 0 else 0.0
        frac = (float(b[1]) / float(b[2])) if len(b) > 2 and b[2] else 0.0
        return a + frac
    return 0.0


def covers(event, t):
    return beat_value(event["startTime"]) <= t <= beat_value(event["endTime"])


def main():
    histogram = {p: collections.Counter() for p in PROPS}
    overlap_fracs = {p: [] for p in PROPS}
    lines_total = 0
    files = sorted(glob.glob("data/packages/*.bin"))

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

        for line in data.get("judgeLineList", []):
            layers = [l for l in (line.get("eventLayers") or []) if l]
            lines_total += 1
            for prop in PROPS:
                defining = [l[prop] for l in layers if l.get(prop)]
                histogram[prop][min(len(defining), 3)] += 1
                if len(defining) < 2:
                    continue
                starts = [min(beat_value(e["startTime"]) for e in evs) for evs in defining]
                ends = [max(beat_value(e["endTime"]) for e in evs) for evs in defining]
                lo, hi = min(starts), max(ends)
                if hi <= lo:
                    continue
                ts = np.linspace(lo, hi, SAMPLES)
                active = np.zeros(SAMPLES, dtype=int)
                for evs in defining:
                    m = np.zeros(SAMPLES, dtype=bool)
                    for e in evs:
                        s, en = beat_value(e["startTime"]), beat_value(e["endTime"])
                        m |= (ts >= s) & (ts <= en)
                    active += m
                overlap_fracs[prop].append(float((active >= 2).mean()))

    print("RPE lines scanned:", lines_total)
    for prop in PROPS:
        hist = histogram[prop]
        vals = overlap_fracs[prop]
        print(f"\n{prop}:")
        print("  layers defining this prop (0,1,2,3+):", dict(hist))
        if vals:
            arr = np.asarray(vals)
            print(f"  lines with >=2 defining layers: {len(vals)}")
            print(f"  overlap fraction  mean={arr.mean():.4f} median={np.median(arr):.4f} "
                  f"p90={np.percentile(arr,90):.4f} max={arr.max():.4f}")
            print(f"  share of these lines with overlap>0.01: {(arr>0.01).mean():.3f}")


if __name__ == "__main__":
    main()
