"""Inspect the structure of a Phira JSON chart file."""

import io
import json
import sys
import zipfile

from phira_pp.api import PhiraClient


def main(chart_id: int):
    client = PhiraClient()
    meta = client.get_chart(chart_id)
    with zipfile.ZipFile(io.BytesIO(client.download_package(meta))) as zf:
        names = zf.namelist()
        member = [n for n in names if n.lower().endswith(".json")][0]
        data = json.loads(zf.read(member))

    print("member", member)
    print("TOP", list(data.keys()))
    print("formatVersion", data.get("formatVersion"), "offset", data.get("offset"))
    for key in ("META", "BPMList", "bpmList", "chartTime", "numOfNotes"):
        if key in data:
            print(key, "=", json.dumps(data[key], ensure_ascii=False)[:300])
    lines = data["judgeLineList"]
    print("NLINES", len(lines))
    print("LINE0KEYS", list(lines[0].keys()))
    print("LINE0", json.dumps(lines[0], ensure_ascii=False)[:1200])


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 26795)
