"""Probe how to get ONE player's record on ONE chart.

Documented /record/query/{chart} only takes page/pageNum, so we test whether an
undocumented player filter exists, and inspect the pool endpoint for a known id.
"""

import json

import requests

BASE = "https://api.phira.cn"
CHART = 26795
USER = 0


def show(tag, resp):
    try:
        data = resp.json()
    except Exception:  # noqa: BLE001
        print(f"{tag:28s} {resp.status_code}  <non-json> {resp.text[:100]}")
        return None
    if isinstance(data, dict):
        rows = None
        for v in data.values():
            if isinstance(v, list):
                rows = v
        head = {k: v for k, v in data.items() if not isinstance(v, list)}
        n = len(rows) if rows is not None else 0
        players = sorted({r.get("player") for r in rows}) if rows else []
        print(f"{tag:28s} {resp.status_code}  keys={list(data.keys())[:6]} count={head.get('count')} "
              f"rows={n} players={players[:6]}")
        return rows
    print(f"{tag:28s} {resp.status_code}  list[{len(data)}]")
    return data


def main():
    s = requests.Session()

    r = s.get(f"{BASE}/record/query/{CHART}", params={"page": 1, "pageNum": 5}, timeout=30)
    rows = show("baseline", r)
    if not rows:
        return
    sample_player = rows[0].get("player")
    print("sample player id:", sample_player)

    for name in ("player", "user", "playerId", "user_id", "uid", "player_id"):
        r = s.get(f"{BASE}/record/query/{CHART}",
                  params={"page": 1, "pageNum": 5, name: sample_player}, timeout=30)
        show(f"filter ?{name}=", r)

    for path in (f"/record/query/{CHART}/{sample_player}",
                 f"/record/query/{CHART}/player/{sample_player}",
                 f"/user/{sample_player}/record",
                 f"/record/user/{sample_player}"):
        try:
            show(path, s.get(f"{BASE}{path}", timeout=30))
        except Exception as exc:  # noqa: BLE001
            print(f"{path:28s} ERR {type(exc).__name__}")

    # does the given user id resolve?
    try:
        u = s.get(f"{BASE}/user/{USER}", timeout=30).json()
        print("user ok:", u.get("id"), u.get("name"), "rks=", u.get("rks"))
    except Exception as exc:  # noqa: BLE001
        print("user lookup ERR", exc)
    try:
        p = s.get(f"{BASE}/record/get-pool/{USER}", timeout=30).json()
        pool = p.get("bestPool", [])
        print(f"pool rows={len(pool)} sample={json.dumps(pool[0], ensure_ascii=False)[:200] if pool else None}")
    except Exception as exc:  # noqa: BLE001
        print("pool ERR", exc)


if __name__ == "__main__":
    main()
