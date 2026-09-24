"""Does the player filter work once authenticated?

/record/best/{chart} returns the *token owner's* best.  Test whether a player
parameter can point it at someone else; chart 16593 is a good probe because
player 289906 has an obvious 1,000,000 AP there.
"""

import requests

from phira_pp.api import load_token

TOKEN = load_token()
S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0"
if TOKEN:
    S.headers["Authorization"] = f"Bearer {TOKEN}"
print("token present:", bool(TOKEN))

HOST = "https://phira.5wyxi.com"
CHART = 16593
ME, OTHER = 0, 289906  # OTHER has score 1000000 on this chart

BASE = S.get(f"{HOST}/record/best/{CHART}", timeout=30)
print(f"baseline (no filter)            -> {BASE.status_code} {BASE.text[:120]}")

print("\n-- on /record/best/{chart}")
for param in ("player", "user", "playerId", "player_id", "user_id", "uid", "id"):
    r = S.get(f"{HOST}/record/best/{CHART}?{param}={OTHER}", timeout=30)
    print(f"   ?{param}={OTHER:<8} -> {r.status_code} {r.text[:110]}")

print("\n-- on /record/query/{chart} (count reveals whether the filter applied)")
base_q = S.get(f"{HOST}/record/query/{CHART}", timeout=30).json()
print(f"   no filter            count={base_q.get('count')} first_player={base_q['results'][0]['player']}")
for param in ("player", "playerId", "user_id", "uid"):
    r = S.get(f"{HOST}/record/query/{CHART}?{param}={OTHER}&page=1&pageNum=30", timeout=30)
    try:
        d = r.json()
    except Exception:  # noqa: BLE001
        print(f"   ?{param}={OTHER:<8} {r.status_code} {r.text[:100]}")
        continue
    res = d.get("results") or []
    print(f"   ?{param}={OTHER:<8} count={d.get('count')} n={len(res)} "
          f"players={sorted({x['player'] for x in res})[:6]}")
