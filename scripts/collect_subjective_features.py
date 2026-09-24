r"""Fetch + cache features for every chart in the subjective 定数表.

Adds the table's charts to ``data/features`` (labels are the Phira 谱师定数, as
usual for the cache; the subjective table is a *separate* label used only by the
experiments).  Failures are counted and listed explicitly, never hidden.

    $env:PYTHONPATH="."; .\.venv\Scripts\python.exe scripts\collect_subjective_features.py
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from phira_pp.api import PhiraClient
from phira_pp.dataset import Dataset

ROOT = Path(__file__).resolve().parent.parent
SUBJECTIVE = ROOT / "data" / "subjective_diff.json"


def main() -> int:
    rows = json.loads(SUBJECTIVE.read_text("utf-8"))["rows"]
    ids = [r["id"] for r in rows]

    client = PhiraClient(token="")
    dataset = Dataset(ROOT / "data", client=client)

    metas = {m.id: m for m in client.get_charts(ids)}
    absent = [i for i in ids if i not in metas]
    print(f"{len(ids)} ids in table; {len(metas)} resolved on Phira; "
          f"{len(absent)} absent (404): {absent}")

    results: dict[int, str] = {}

    def one(cid: int) -> tuple[int, str]:
        try:
            feats = dataset.get_features(metas[cid])
        except Exception as exc:  # noqa: BLE001 - counted below
            return cid, f"error:{type(exc).__name__}"
        if feats is None:
            return cid, "unsupported-format"
        return cid, "ok"

    with ThreadPoolExecutor(max_workers=8) as ex:
        for cid, status in ex.map(one, sorted(metas)):
            results[cid] = status

    by = {}
    for cid, status in results.items():
        by.setdefault(status, []).append(cid)
    for status, cs in sorted(by.items()):
        print(f"  {status:20} {len(cs)}")
    bad = [c for s in ("unsupported-format",) + tuple(k for k in by if k.startswith("error"))
           for c in by.get(s, [])]
    if bad:
        print("non-ok ids:", sorted(bad))
    return 0


if __name__ == "__main__":
    sys.exit(main())
