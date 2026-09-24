"""Re-extract features for every cached package (offline, no downloads).

Bumping ``FEATURES_VERSION`` invalidates the on-disk cache; this rebuilds it from
``data/packages/*.bin`` so new features can be evaluated without re-downloading.
The label/provenance fields (``_difficulty``/``_ranked``/``_rating_count``) are
carried over from the existing JSON so the training set is unchanged.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from phira_pp.features import FEATURES_VERSION, extract_features
from phira_pp.loader import load_package

ROOT = Path("data")
PKG = ROOT / "packages"
FEAT = ROOT / "features"
KEEP = ("_difficulty", "_ranked", "_rating_count")


def main() -> int:
    force = "--force" in sys.argv      # needed when a feature CONSTANT changed
    ok = fail = versioned = 0
    failures: list[int] = []
    for path in sorted(PKG.glob("*.bin")):
        cid = int(path.stem)
        old = FEAT / f"{cid}.json"
        keep = {}
        if old.exists():
            try:
                cached = json.loads(old.read_text("utf-8"))
                keep = {k: cached[k] for k in KEEP if k in cached}
                if cached.get("_version") == FEATURES_VERSION and not force:
                    versioned += 1
                    continue          # already current
            except Exception:  # noqa: BLE001 - rebuild it
                pass
        try:
            chart = load_package(path.read_bytes())
            feats = extract_features(chart)
        except Exception:  # noqa: BLE001 - reported below, never hidden
            feats = None
        if feats is None:
            fail += 1
            failures.append(cid)
            continue
        feats.update(keep)
        feats["_format"] = chart.chart_format
        feats["_note_count"] = chart.note_count
        feats["_version"] = FEATURES_VERSION
        old.write_text(json.dumps(feats), "utf-8")
        ok += 1
        if (ok + versioned) % 100 == 0:
            print(f"  {ok + versioned} charts ...", flush=True)

    print(f"re-extracted {ok}, already current {versioned}, failed {fail}")
    if failures:
        print("failed ids:", failures[:40])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
