import collections
import io
import sys
import zipfile

import requests

API = "https://api.phira.cn"


def load_package(chart_id):
    meta = requests.get(f"{API}/chart/{chart_id}", timeout=60).json()
    blob = requests.get(meta["file"], timeout=180).content
    zf = zipfile.ZipFile(io.BytesIO(blob))
    return meta, zf


def main(chart_id):
    meta, zf = load_package(chart_id)
    print("chart", chart_id, meta["name"], meta["level"], meta["difficulty"])
    print("members", zf.namelist())
    pec = [n for n in zf.namelist() if n.lower().endswith(".pec")]
    if not pec:
        print("no .pec in package")
        return
    text = zf.read(pec[0]).decode("utf-8", errors="replace")
    lines = [l for l in text.splitlines() if l.strip()]
    print("lines", len(lines), "first", repr(lines[0]))

    for pre in ("n1", "n2", "n3", "n4"):
        rows = [l.split() for l in lines if l.startswith(pre + " ")]
        counts = collections.Counter(len(r) for r in rows)
        print(pre, "rows", len(rows), "argcounts", dict(counts))
        for n in sorted(counts):
            subset = [r for r in rows if len(r) == n]
            for c in range(1, n):
                vals = []
                for r in subset:
                    try:
                        vals.append(float(r[c]))
                    except ValueError:
                        pass
                if vals:
                    print(
                        f"   col{c} min={min(vals):.3f} max={max(vals):.3f} distinct={sorted(set(vals))[:8]}"
                    )
            # group by full tail signature to spot type/hold variety
            sigs = collections.Counter(tuple(r[1:]) for r in subset)
            print("   sample", subset[:2], "distinct_tails", len(sigs))

    cmds = collections.Counter(l.split()[0] for l in lines)
    print("commands", dict(cmds))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 51)
