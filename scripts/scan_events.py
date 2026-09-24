"""Scan cached chart packages to learn how real charts use line events.

Answers, from real data:
  * which formats are present
  * for RPE: how many non-null eventLayers lines actually use, which event
    arrays appear, and whether moveX/moveY are separate
  * for PEC: which event commands are actually used
"""

import collections
import glob
import io
import json
import zipfile


def chart_member(names):
    for ext in (".pec", ".json", ".pbc"):
        for n in names:
            if n.lower().endswith(ext):
                return n
    return None


def scan_rpe(data, agg):
    lines = data.get("judgeLineList", [])
    layer_hist = collections.Counter()
    event_arrays = collections.Counter()
    for ln in lines:
        layers = ln.get("eventLayers") or []
        nonnull = [l for l in layers if l]
        layer_hist[len(nonnull)] += 1
        for layer in nonnull:
            for key, val in layer.items():
                if isinstance(val, list) and val:
                    event_arrays[key] += 1
    agg["layer_hist"].update(layer_hist)
    agg["event_arrays"].update(event_arrays)
    agg["rpe_lines"] += len(lines)


def main():
    files = sorted(glob.glob("data/packages/*.bin"))
    formats = collections.Counter()
    agg = {
        "layer_hist": collections.Counter(),
        "event_arrays": collections.Counter(),
        "pec_cmds": collections.Counter(),
        "rpe_lines": 0,
    }

    for path in files:
        try:
            with zipfile.ZipFile(path) as zf:
                member = chart_member(zf.namelist())
                raw = zf.read(member) if member else b""
        except Exception as exc:  # noqa: BLE001
            formats[f"ERR:{type(exc).__name__}"] += 1
            continue
        if not raw:
            formats["empty"] += 1
            continue

        if raw[:1].lstrip().startswith(b"{"):
            try:
                data = json.loads(raw)
            except Exception:  # noqa: BLE001
                formats["json_err"] += 1
                continue
            if isinstance(data, dict) and ("META" in data or "BPMList" in data):
                formats["rpe"] += 1
                scan_rpe(data, agg)
            else:
                formats["phi"] += 1
        else:
            formats["pec"] += 1
            text = raw.decode("utf-8", errors="replace")
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                head = line.split(maxsplit=1)[0]
                if head in ("cv", "cp", "cm", "cd", "ca", "cr", "cf", "bp"):
                    agg["pec_cmds"][head] += 1

    print("packages:", len(files))
    print("formats:", dict(formats))
    print("RPE lines:", agg["rpe_lines"])
    print("RPE non-null eventLayers per line:", dict(agg["layer_hist"]))
    print("RPE event arrays (count of lines using each):", dict(agg["event_arrays"]))
    print("PEC event commands:", dict(agg["pec_cmds"]))


if __name__ == "__main__":
    main()
