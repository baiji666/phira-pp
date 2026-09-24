"""Resolve 定数表 cards (title + group) to chart ids, verified by name.

Candidate sources, in order of preference:
  1. the user's own played charts (from data/user_scores_*.json) — their names are
     fetched from the API; this disambiguates titles that search alone cannot;
  2. /chart?search=<title> (with a shortened fallback query).
A card is kept only when exactly ONE candidate matches by name and is within
``window`` of the table's group value; everything else is reported, not guessed.
"""

import argparse
import json
import re
from pathlib import Path

from phira_pp.api import PhiraClient

RAW = Path("data/anchor_table_raw.json")
OUT = Path("data/anchors.json")
KEEP = re.compile(r"[0-9a-z\u4e00-\u9fff\u3040-\u30ff]")
MIN_PREFIX = 4


def norm(s: str) -> str:
    return "".join(KEEP.findall(s.lower()))


def matches(name: str, title: str) -> bool:
    n, t = norm(name), norm(title)
    if not n or not t:
        return False
    if n == t:
        return True
    if len(t) < MIN_PREFIX or len(n) < MIN_PREFIX:
        return False
    return n.startswith(t) or t.startswith(n)


def queries(title: str) -> list[str]:
    out = [title]
    head = re.split(r"[\(（\[]", title)[0].strip()
    if head and head != title:
        out.append(head)
    for cut in (14, 10):
        if len(title) > cut:
            out.append(title[:cut])
    seen, uniq = set(), []
    for q in out:
        if q and q not in seen:
            seen.add(q)
            uniq.append(q)
    return uniq


def main(window: float = 1.2, strict: bool = False):
    raw = json.loads(RAW.read_text("utf-8"))
    client = PhiraClient()

    played: dict[int, tuple[str, float, bool]] = {}
    for path in Path("data").glob("user_scores_*.json"):
        ids = [int(k) for k in json.loads(path.read_text("utf-8"))["scores"]]
        print(f"{path.name}: {len(ids)} played chart ids")
        for meta in client.get_charts(ids):
            played[meta.id] = (meta.name, float(meta.difficulty), bool(meta.ranked))
    print(f"resolved names for {len(played)} played charts")

    search_cache: dict[str, list] = {}
    rows_found: list[dict] = []          # every (card, candidate) pair
    card_multi = 0
    missing = []

    for e in raw["entries"]:
        title, group = e["title"], float(e["group"])
        cands = []
        for cid, (name, diff, ranked) in played.items():
            if matches(name, title) and abs(diff - group) <= window:
                cands.append((cid, name, diff, ranked, "played"))
        rows = []
        for q in queries(title):
            if q not in search_cache:
                try:
                    d = client.search_charts(search=q, pageNum=20)
                    search_cache[q] = d.get("results") or []
                except Exception as exc:  # noqa: BLE001 - surface, never hide
                    print(f"  ! search failed {q!r}: {type(exc).__name__}")
                    search_cache[q] = []
            rows += search_cache[q]
            if any(matches(r["name"], title) for r in rows):
                break
        for r in rows:
            if matches(r["name"], title) and abs(float(r["difficulty"]) - group) <= window:
                cands.append((r["id"], r["name"], float(r["difficulty"]), bool(r["ranked"]), "search"))

        uniq = {c[0]: c for c in cands}
        cands = list(uniq.values())
        if not cands:
            missing.append((title, group))
            continue
        # A song may legitimately have several Phira charts (the user's point):
        # keep them all as distinct charts.  In strict mode we only keep
        # single-candidate cards.
        if strict and len(cands) > 1:
            missing.append((title, group))
            continue
        if len(cands) > 1:
            card_multi += 1
        for cid, name, diff, ranked, src in cands:
            rows_found.append({"page": e["page"], "group": group, "id": cid, "name": name,
                               "charter_diff": diff, "ranked": ranked, "via": src,
                               "n_candidates": len(cands)})

    # one chart may be claimed by several cards; keep the closest to its charter 定数
    by_id: dict[int, list[dict]] = {}
    for r in rows_found:
        by_id.setdefault(r["id"], []).append(r)
    resolved, conflicts = [], []
    for cid, claims in by_id.items():
        groups = {c["group"] for c in claims}
        if len(groups) > 1:
            conflicts.append((cid, claims[0]["name"], sorted(groups)))
        best = min(claims, key=lambda c: abs(c["group"] - c["charter_diff"]))
        resolved.append(best)

    total = len(raw["entries"])
    print(f"\nentries={total}  cards->charts={len(rows_found)}  unique_charts={len(resolved)}  "
          f"cards_with_multiple_charts={card_multi}  conflicts={len(conflicts)}  "
          f"unresolved_cards={len(missing)}  (window=±{window}, strict={strict})")
    if resolved:
        import numpy as np
        d = np.asarray([r["group"] - r["charter_diff"] for r in resolved])
        print(f"group - charter_diff: mean={d.mean():+.3f} std={d.std():.3f} "
              f"min={d.min():+.2f} max={d.max():+.2f} |Δ|>0.5: {(abs(d)>0.5).mean():.1%}")
        print(f"resolved ranked={sum(r['ranked'] for r in resolved)}/{len(resolved)}")
        print("by group:", {g: sum(1 for r in resolved if r["group"] == g)
                            for g in sorted({r["group"] for r in resolved}, reverse=True)})
    if conflicts:
        print(f"\n{len(conflicts)} charts claimed by several cards, e.g.:")
        for cid, name, gs in conflicts[:6]:
            print(f"  #{cid} {name[:28]!r} groups={gs}")
    if missing:
        print(f"\nunresolved cards: {len(missing)}, first 10: {[t for t, _ in missing[:10]]}")

    OUT.write_text(json.dumps({"resolved": resolved,
                               "conflicts": [{"id": c, "name": n, "groups": g} for c, n, g in conflicts],
                               "unresolved": [t for t, _ in missing]},
                              ensure_ascii=False, indent=1), "utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=float, default=1.2)
    ap.add_argument("--strict", action="store_true",
                    help="keep only cards that match exactly one chart (old behaviour)")
    a = ap.parse_args()
    main(a.window, strict=a.strict)
