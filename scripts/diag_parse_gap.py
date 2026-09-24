"""Diagnose charts whose package our parser cannot handle."""

import io
import json
import zipfile

from phira_pp.api import PhiraClient
from phira_pp.loader import load_package

IDS = [76959, 76993, 76851, 77421, 72429]
client = PhiraClient()

for cid in IDS:
    try:
        meta = client.get_chart(cid)
    except Exception as exc:  # noqa: BLE001
        print(f"#{cid}: meta error {type(exc).__name__}")
        continue
    try:
        blob = client.download_package(meta)
        zf = zipfile.ZipFile(io.BytesIO(blob))
        names = zf.namelist()
        member = [n for n in names if n.lower().endswith((".pec", ".json", ".pbc"))]
        info = zf.read(member[0])[:1] if member else b"?"
        print(f"#{cid} {meta.name!r} notes_file={member} first_byte={info!r}")
        for name in names:
            if name.lower().endswith(".yml"):
                print("   ", name, "->", zf.read(name).decode("utf-8", "replace")[:220].replace("\n", " | "))
        chart = load_package(blob, name=meta.name)
        print(f"   parsed ok: notes={chart.note_count} fmt={chart.chart_format}")
    except Exception as exc:  # noqa: BLE001
        print(f"#{cid} {meta.name!r} PARSE FAIL: {type(exc).__name__}: {str(exc)[:130]}")
