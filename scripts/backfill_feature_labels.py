r"""Repair ``data/features/*.json`` entries that are missing their label.

A feature cache entry carries the label/provenance it was built with
(``_difficulty`` / ``_ranked`` / ``_rating_count``).  Some entries on disk have
only ``_format`` / ``_note_count`` / ``_version``: those came from a
``reextract_features.py`` pass whose source file already lacked a label, and
they could never be repaired because ``Dataset.get_features`` returned cache
hits without rewriting provenance (fixed) — so ``build_train_set.py``'s
"backfill" silently did nothing.

This tool refetches the *metadata* only (no package downloads: every one of
these already has a local ``.bin``), stores the label, and reports anything it
could not repair.  Querying/PP is unaffected either way — D* only needs the
features, never the label — so this is purely about restoring the D* training set.

    $env:PYTHONPATH="."; .\.venv\Scripts\python.exe scripts/backfill_feature_labels.py [--apply]
"""

from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

from phira_pp.api import PhiraClient
from phira_pp.dataset import Dataset
from phira_pp.features import FEATURES_VERSION, FEATURE_NAMES


def main() -> int:
    apply = "--apply" in sys.argv
    feat_dir = Path("data/features")
    need: list[int] = []
    for path in glob.glob(str(feat_dir / "*.json")):
        try:
            f = json.loads(Path(path).read_text("utf-8"))
        except Exception as exc:  # noqa: BLE001 - reported
            print(f"  ! unreadable {path}: {type(exc).__name__}")
            continue
        if f.get("_version") != FEATURES_VERSION or not all(k in f for k in FEATURE_NAMES):
            continue
        if not isinstance(f.get("_difficulty"), (int, float)):
            need.append(int(Path(path).stem))

    print(f"cached feature files missing a label: {len(need)}")
    if not need:
        print("nothing to repair")
        return 0
    if not apply:
        print("dry run (pass --apply to write); sample:", sorted(need)[:10])
        return 0

    client = PhiraClient(token="")
    dataset = Dataset("data", client=client)
    metas = {m.id: m for m in client.get_charts(need)}
    absent = sorted(set(need) - set(metas))

    repaired, failed = 0, []
    for cid in need:
        meta = metas.get(cid)
        if meta is None:
            continue
        try:
            dataset.get_features(meta)          # now persists provenance on a hit
        except Exception as exc:  # noqa: BLE001 - counted, never hidden
            failed.append((cid, type(exc).__name__))
            continue
        f = json.loads((feat_dir / f"{cid}.json").read_text("utf-8"))
        if isinstance(f.get("_difficulty"), (int, float)):
            repaired += 1

    print(f"repaired: {repaired}")
    print(f"absent from the Phira API (no meta -> cannot label): {len(absent)} {absent}")
    if failed:
        print(f"failed: {len(failed)} {failed}")
    still = [cid for cid in need if cid not in metas]
    if still or failed:
        print("NOT repaired (explicit, not hidden):",
              sorted(still) + [c for c, _ in failed])
    return 0


if __name__ == "__main__":
    sys.exit(main())
