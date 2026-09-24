r"""Check ``docs/formula.md`` against the live source of truth.

The doc duplicates numbers from ``pp.py`` / ``pipeline.py`` /
``data/difficulty_model.json``; project_rules.md requires them to be verified
whenever a source changes.  Run this after any of those edits.

    $env:PYTHONPATH="."; .\.venv\Scripts\python.exe scripts/verify_formula_doc.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from phira_pp.dataset import load_model
from phira_pp.pp import STD_PLAUSIBLE_MAX, PPParams
from phira_pp.pipeline import OSU_DECAY

DOC = Path(__file__).resolve().parent.parent / "docs" / "formula.md"
MODEL = Path(__file__).resolve().parent.parent / "data" / "difficulty_model.json"
NUM = re.compile(r"[-−+]?\d+(?:\.\d+)?")
EPS = 6e-5
failures: list[str] = []


def num(s: str) -> float | None:
    m = NUM.search(s.replace("**", ""))
    if not m:
        return None
    return float(m.group(0).replace("−", "-"))


def cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def main() -> int:
    doc = DOC.read_text("utf-8")
    model = load_model(MODEL)
    params = PPParams()

    print(f"[§5] {len(model.names)} features x (w, mu, sigma) vs data/difficulty_model.json")
    checked = 0
    rows = [ln for ln in doc.splitlines() if ln.startswith("| ") and "`" in ln]
    for ln in rows:
        c = cells(ln)
        if len(c) < 6:
            continue
        name = c[1].strip("`* ")
        if name not in model.names:
            continue
        i = model.names.index(name)
        want = (float(model.weights[i]), float(model.mean[i]), float(model.std[i]))
        got = (num(c[3]), num(c[4]), num(c[5]))
        for label, g, w in zip(("w", "mu", "sigma"), got, want):
            if g is None or abs(g - w) > EPS:
                failures.append(f"§5 {name}.{label}: doc={g} model={w:.6f}")
            checked += 1
    print(f"      feature values checked: {checked} (expect {len(model.names) * 3})")

    bias_line = [ln for ln in rows if "bias" in ln and num(ln) is not None]
    if bias_line:
        g = num(cells(bias_line[0])[3])
        if g is None or abs(g - float(model.bias)) > EPS:
            failures.append(f"§5 bias: doc={g} model={model.bias:.6f}")
        else:
            print(f"      bias OK ({model.bias:.4f})")

    print("[§3] PPParams / constants vs phira_pp.pp & pipeline")
    known = {k: float(v) for k, v in vars(params).items()}
    known["STD_PLAUSIBLE_MAX"] = float(STD_PLAUSIBLE_MAX)
    known["OSU_DECAY"] = float(OSU_DECAY)
    pchecked = 0
    for ln in rows:
        c = cells(ln)
        for i, cand in enumerate(c[:-1]):
            key = cand.strip("`* ")
            if key not in known:
                continue
            g = num(c[i + 1])
            if g is None or abs(g - known[key]) > 1e-9:
                failures.append(f"§3 {key}: doc={g} source={known[key]}")
            pchecked += 1
            break
    print(f"      parameter rows checked: {pchecked}")

    print()
    if failures:
        print(f"FAILED: {len(failures)} mismatch(es)")
        for f in failures:
            print("   " + f)
        return 1
    print("docs/formula.md is consistent with the source")
    return 0


if __name__ == "__main__":
    sys.exit(main())
