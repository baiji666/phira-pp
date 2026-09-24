"""How deep can /record/query/{chart} be paged? Decides the player-search cap."""

import requests

BASE = "https://api.phira.cn"
CHART = 26795


def main():
    s = requests.Session()
    seen = set()
    for page in range(1, 9):
        r = s.get(f"{BASE}/record/query/{CHART}",
                  params={"page": page, "pageNum": 30}, timeout=30)
        data = r.json()
        rows = data.get("results", [])
        ids = {row.get("id") for row in rows}
        new = ids - seen
        seen |= ids
        print(f"page={page} rows={len(rows)} new={len(new)} cumulative_ids={len(seen)} "
              f"count_field={data.get('count')}")


if __name__ == "__main__":
    main()
