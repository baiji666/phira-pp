"""Build the single-file ``PhiraPP.html`` (no server, no install).

Injects the community 定数 tables (id -> 定数) into
``web/standalone.template.html`` and writes ``PhiraPP.html`` into the project
root: the Suonasi KV table, then the subjective 定数表 for the ids Suonasi does
not cover (Suonasi wins on overlap).

The subjective values are then raised to D* where D* is higher -- the same
"主观表 is a floor" rule the Python engine applies (see
``phira_pp.pipeline._table_with_floor``), reproduced here from the cached
features so the single file keeps agreeing with ``scripts/pp.py best``.  Charts
without cached features keep the table value and are counted.

Re-run after refreshing ``data/kv_diff.json`` / ``data/subjective_diff.json`` /
``data/difficulty_model.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

from phira_pp.dataset import load_model
from phira_pp.features import FEATURES_VERSION, FEATURE_NAMES
from phira_pp.pipeline import _dstar_usable

ROOT = Path(__file__).resolve().parent.parent
KV_FILE = ROOT / "data" / "kv_diff.json"
SUBJECTIVE_FILE = ROOT / "data" / "subjective_diff.json"
MODEL_FILE = ROOT / "data" / "difficulty_model.json"
TEMPLATE = ROOT / "web" / "standalone.template.html"
OUT = ROOT / "PhiraPP.html"
PLACEHOLDER = "__KV_TABLE_JSON__"


def _cached_d_star(cid: int, model) -> float | None:
    path = ROOT / "data" / "features" / f"{cid}.json"
    if not path.exists():
        return None
    try:
        f = json.loads(path.read_text("utf-8"))
    except Exception:  # noqa: BLE001 - treated as "no cached features"
        return None
    if f.get("_version") != FEATURES_VERSION or not all(k in f for k in FEATURE_NAMES):
        return None
    return float(model.predict_features({k: f[k] for k in FEATURE_NAMES}))


def main() -> int:
    table: dict[str, float] = {}

    kv = json.loads(KV_FILE.read_text("utf-8"))
    for r in kv.get("rows", kv) if isinstance(kv, dict) else kv:
        table[str(int(r["id"]))] = float(r["difficulty"])

    subj_only: list[int] = []
    if SUBJECTIVE_FILE.exists():
        subj = json.loads(SUBJECTIVE_FILE.read_text("utf-8"))
        for r in subj.get("rows", []):
            key = str(int(r["id"]))
            if key in table:                    # Suonasi wins on overlap
                continue
            table[key] = float(r["difficulty"])
            subj_only.append(int(r["id"]))

    if subj_only:
        model = load_model(MODEL_FILE)
        raised = missing = 0
        for cid in subj_only:
            d = _cached_d_star(cid, model)
            if d is None:
                missing += 1
                continue
            if _dstar_usable(d) and d > table[str(cid)]:
                table[str(cid)] = d
                raised += 1
        print(f"subjective floor: raised {raised}/{len(subj_only)} charts"
              + (f"  ({missing} without cached features -> table value kept)" if missing else ""))

    ov_path = ROOT / "data" / "difficulty_override.json"
    if ov_path.exists():
        ov_rows = json.loads(ov_path.read_text("utf-8")).get("rows", [])
        for r in ov_rows:
            table[str(int(r["id"]))] = float(r["value"])
        print(f"expert overrides baked in: {len(ov_rows)}")

    html = TEMPLATE.read_text("utf-8")
    if PLACEHOLDER not in html:
        print(f"ERROR: {PLACEHOLDER} not found in {TEMPLATE.name}")
        return 1
    html = html.replace(PLACEHOLDER,
                        json.dumps(table, ensure_ascii=False, separators=(",", ":")))
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT.name}: {len(html.encode('utf-8'))} bytes, {len(table)} charts embedded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
