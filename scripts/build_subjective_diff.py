r"""Build ``data/subjective_diff.json`` from the user's subjective 定数 table.

Source: ``data/subjective_diff.xlsx`` (phira 高难自制谱面参考性主观定数表), a
human 体感定数 table.  Columns: 曲名 | 谱师 | 定数 | 加分项 | 上架谱编号.

Rules (from the table's own note, and the requester):
* rows whose 上架谱编号 is ``/`` are **local charts** -> dropped;
* the table is capped below 18.60 ("不会对 18.60 及以上进行定数");
* on overlap with the Suonasi KV table the **KV value wins** (handled in
  ``load_tables``, not here) — this file still lists every published id so the
  decision is auditable.

The xlsx is parsed with the stdlib only (zipfile + ElementTree); the project
venv has no openpyxl.

Usage:
    $env:PYTHONPATH="."; .\.venv\Scripts\python.exe scripts/build_subjective_diff.py
    ... scripts/build_subjective_diff.py --verify   # also cross-check names/ranked via the live API
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_XLSX = ROOT / "data" / "subjective_diff.xlsx"
DEFAULT_OUT = ROOT / "data" / "subjective_diff.json"
SOURCE = "phira高难自制谱面参考性主观定数表（用户提供的 xlsx，见 data/subjective_diff.xlsx）"


def _col_to_idx(ref: str) -> int:
    letters = re.match(r"([A-Z]+)", ref).group(1)
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch) - 64)
    return idx - 1


def _shared_strings(z: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in si.iter(f"{NS}t"))
            for si in root.findall(f"{NS}si")]


def _sheet_rows(z: zipfile.ZipFile, shared: list[str], sheet: str) -> list[list]:
    root = ET.fromstring(z.read(sheet))
    rows: list[list] = []
    for row in root.iter(f"{NS}row"):
        cells: dict[int, object] = {}
        for c in row.findall(f"{NS}c"):
            t = c.get("t")
            v = c.find(f"{NS}v")
            isel = c.find(f"{NS}is")
            if t == "s" and v is not None:
                val: object = shared[int(v.text)]
            elif t == "inlineStr" and isel is not None:
                val = "".join(x.text or "" for x in isel.iter(f"{NS}t"))
            elif v is not None:
                val = v.text
            else:
                val = None
            cells[_col_to_idx(c.get("r"))] = val
        rows.append([cells.get(i) for i in range(max(cells) + 1)] if cells else [])
    return rows


def parse(xlsx: Path) -> list[dict]:
    """Published-id rows only, in table order."""
    with zipfile.ZipFile(xlsx) as z:
        shared = _shared_strings(z)
        rows = _sheet_rows(z, shared, "xl/worksheets/sheet1.xml")

    out: list[dict] = []
    group = None
    for r in rows[1:]:
        name = (r[0] or "").strip() if len(r) > 0 and r[0] else ""
        if not name:
            continue
        if re.fullmatch(r"\d+\.\d+x", name):
            group = name                       # section header, e.g. "18.5x"
            continue
        diff = r[2] if len(r) > 2 else None
        raw_id = r[4] if len(r) > 4 else None
        if diff is None or str(diff).strip() == "":
            continue                            # the header note / blank rows
        try:
            dval = float(str(diff).strip())
        except ValueError:
            print(f"WARN: skipped row with unparsable 定数: {r!r}")
            continue
        m = re.search(r"(\d+)", str(raw_id)) if raw_id else None
        if not m:
            continue                            # 上架谱编号 "/" -> local chart, dropped
        cid = int(m.group(1))
        out.append({
            "id": cid,
            "name": name,
            "difficulty": dval,
            "charter": (r[1] or "").strip() if len(r) > 1 and r[1] else "",
            "bonus": (r[3] or "").strip() if len(r) > 3 and r[3] else "",
            "group": group,
        })
    return out


def _norm(s: str) -> str:
    """Loose title comparison only; the chart id is the authoritative key."""
    for a, b in (("（", "("), ("）", ")"), ("，", ","), ("：", ":"), ("　", ""),
                 (" ", ""), ("・", ""), ("·", ""), ("◆", ""), ("〈", ""), ("〉", "")):
        s = s.replace(a, b)
    return s.strip().lower()


def verify(rows: list[dict]) -> int:
    from phira_pp.api import PhiraClient

    client = PhiraClient(token="")
    metas = {m.id: m for m in client.get_charts([r["id"] for r in rows])}
    missing, mismatch, ranked = [], [], []
    for r in rows:
        m = metas.get(r["id"])
        if m is None:
            missing.append(r["id"])
            continue
        if _norm(m.name) != _norm(r["name"]):
            mismatch.append((r["id"], r["name"], m.name))
        if m.ranked and m.difficulty > 0:
            ranked.append((r["id"], r["name"], m.difficulty, r["difficulty"]))
    print(f"verify: {len(rows)} ids, resolved {len(metas)}")
    print(f"  not found on Phira API : {len(missing)} {missing}")
    print(f"  name mismatch          : {len(mismatch)}")
    for i, a, b in mismatch:
        print(f"     {i}  xlsx={a!r}  api={b!r}")
    print(f"  ranked (charter 定数 will outrank this table) : {len(ranked)}")
    for i, n, md, sd in ranked:
        print(f"     {i} {n}  ranked 定数={md}  主观={sd}")
    return 0 if not missing else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--verify", action="store_true",
                    help="cross-check every id against the live Phira API")
    args = ap.parse_args()

    rows = parse(args.xlsx)
    ids = [r["id"] for r in rows]
    dups = sorted({i for i in ids if ids.count(i) > 1})
    if dups:
        print(f"ERROR: duplicate chart ids in table: {dups}")
        return 1
    if not rows:
        print("ERROR: no published-id rows parsed")
        return 1

    dvals = [r["difficulty"] for r in rows]
    payload = {"source": SOURCE, "rows": rows}
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), "utf-8")
    print(f"parsed {len(rows)} published-id rows (dropped local '/' charts)")
    print(f"定数 range: {min(dvals)} - {max(dvals)}")
    print(f"wrote {args.out.relative_to(ROOT)}")

    if args.verify:
        return verify(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
