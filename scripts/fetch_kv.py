"""Fetch the machine-readable 定数表 published by the SuonasiOS app's own KV
service (discovered in libapp.so) and use it as the anchor table.

    https://suonasi.07210700.xyz/kv/diff

The APK also ships a local copy at assets/flutter_assets/assets/catalog/diff.tsv.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import requests

DIFF_URL = "https://suonasi.07210700.xyz/kv/diff"
UA = "Mozilla/5.0"


def parse_diff(text: str) -> list[dict]:
    """Parse the ``id/name/diff/badge/cover`` TSV (rows are not reliably
    single-tab separated, so the id and difficulty are matched by position)."""
    out: list[dict] = []
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        m = re.match(r"^(\d+)\t(.+?)\t(\d+(?:\.\d+)?)(?:\t(.*?))?(?:\t(.*))?$", line)
        if m:
            out.append({
                "id": int(m.group(1)),
                "name": m.group(2).strip(),
                "difficulty": float(m.group(3)),
                "level": (m.group(4) or "").strip(),
            })
    return out


def fetch_diff(url: str = DIFF_URL, timeout: float = 30.0) -> list[dict]:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
    r.raise_for_status()
    return parse_diff(r.text)


def main():
    raw = requests.get(DIFF_URL, headers={"User-Agent": UA}, timeout=30).text
    rows = parse_diff(raw)
    print(f"parsed {len(rows)} rows")
    if not rows:
        return
    diffs = [r["difficulty"] for r in rows]
    print(f"difficulty range {min(diffs):.1f}-{max(diffs):.1f}")
    print(">=17.0:", sum(1 for d in diffs if d >= 17.0))
    local = [l for l in raw.splitlines() if re.match(r"^-\d+\t", l)]
    bad = [l for l in raw.splitlines() if l.strip() and not l.startswith("#")
           and not re.match(r"^\d+\t", l) and not re.match(r"^-\d+\t", l)]
    print(f"local-only rows (negative id, not on Phira, skipped): {len(local)}")
    print(f"unparsed non-header lines: {len(bad)}", bad[:3])

    ids = {r["id"] for r in rows}
    old = Path("data/anchors.json")
    if old.exists():
        prev = json.loads(old.read_text("utf-8"))
        prev_ids = {r["id"] for r in prev.get("resolved", [])}
        print(f"\nold OCR anchors: {len(prev_ids)}  ->  overlap {len(ids & prev_ids)}")
        print(f"new ids not in OCR set: {len(ids - prev_ids)}")
        print(f"OCR ids missing from KV: {len(prev_ids - ids)}")
        sample = sorted(prev_ids - ids)[:8]
        if sample:
            print("  e.g. absent:", sample)

    Path("data/kv_diff.json").write_text(
        json.dumps({"source": DIFF_URL, "rows": rows}, ensure_ascii=False, indent=1), "utf-8")
    print(f"\nsaved -> data/kv_diff.json ({len(rows)} rows)")


if __name__ == "__main__":
    main()
