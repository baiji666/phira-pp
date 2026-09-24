"""Find and explain extreme line-position values in real RPE charts."""

import glob
import json
import zipfile

import numpy as np

from phira_pp.beats import parse_beat
from phira_pp.lineevents import RpeLineSet

THRESHOLD = 1e5


def main():
    files = sorted(glob.glob("data/packages/*.bin"))
    shown = 0
    for path in files:
        try:
            with zipfile.ZipFile(path) as zf:
                members = [n for n in zf.namelist() if n.lower().endswith(".json")]
                data = json.loads(zf.read(members[0]))
        except Exception:  # noqa: BLE001
            continue
        if not (isinstance(data, dict) and ("META" in data or "BPMList" in data)):
            continue
        lines_raw = data.get("judgeLineList", [])
        lines = RpeLineSet(lines_raw)
        beats = [parse_beat(n["startTime"]) for ln in lines_raw for n in ln.get("notes", [])]
        if not beats:
            continue
        lo, hi = min(beats), max(beats)
        for i, ln in enumerate(lines_raw):
            worst = None
            for b in np.linspace(lo, hi, 40):
                x, y = lines.pos(i, float(b))
                if max(abs(x), abs(y)) > THRESHOLD:
                    worst = (float(b), x, y)
                    break
            if worst is None:
                continue
            print(f"\n{path} #{data.get('META', {}).get('id')} line {i} beat={worst[0]:.1f} "
                  f"pos=({worst[1]:.0f}, {worst[2]:.0f})")
            for li, layer in enumerate(ln.get("eventLayers") or []):
                if not layer:
                    continue
                for key in ("moveXEvents", "moveYEvents"):
                    evs = layer.get(key)
                    if evs:
                        print(f"  layer{li} {key}:")
                        for e in evs[:4]:
                            print("   ", e.get("startTime"), e.get("endTime"),
                                  "start=", e.get("start"), "end=", e.get("end"),
                                  "easing=", e.get("easingType"))
            shown += 1
            if shown >= 3:
                return
    print("no extreme lines found")


if __name__ == "__main__":
    main()
