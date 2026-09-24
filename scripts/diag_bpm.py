"""Find charts containing implausible BPM values and locate them in the timeline."""

import glob
import json
import zipfile

from phira_pp.beats import parse_beat


def main():
    for path in sorted(glob.glob("data/packages/*.bin")):
        try:
            with zipfile.ZipFile(path) as zf:
                members = [n for n in zf.namelist() if n.lower().endswith(".json")]
                data = json.loads(zf.read(members[0]))
        except Exception:  # noqa: BLE001
            continue
        if not (isinstance(data, dict) and ("META" in data or "BPMList" in data)):
            continue
        bpm_list = data.get("BPMList") or []
        bad = [p for p in bpm_list if float(p.get("bpm", 0)) > 1000 or float(p.get("bpm", 0)) <= 0]
        if not bad:
            continue
        note_beats = [parse_beat(n["startTime"])
                      for ln in data.get("judgeLineList", []) for n in ln.get("notes", [])]
        hi = max(note_beats) if note_beats else 0.0
        print(f"\n{path} #{data.get('META', {}).get('id')}  nBPM={len(bpm_list)} "
              f"lastNoteBeat={hi:.1f}")
        for p in bpm_list[:6]:
            print("   ", p.get("startTime"), "bpm=", p.get("bpm"))
        for p in bad[:6]:
            print("  BAD", p.get("startTime"), "bpm=", p.get("bpm"),
                  "beat=", round(parse_beat(p["startTime"]), 2), "<=lastNote:", parse_beat(p["startTime"]) <= hi)


if __name__ == "__main__":
    main()
