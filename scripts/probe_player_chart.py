"""Characterise /record?player={user}&chart={chart} (the real player x chart API)."""

import json

import requests

from phira_pp.api import load_token

H = "https://phira.5wyxi.com"
U = 0

bare = requests.Session()
bare.headers["User-Agent"] = "Mozilla/5.0"

auth = requests.Session()
auth.headers["User-Agent"] = "Mozilla/5.0"
tok = load_token()
if tok:
    auth.headers["Authorization"] = f"Bearer {tok}"


def probe(label, sess, path):
    try:
        r = sess.get(f"{H}{path}", timeout=30)
        j = r.json()
    except Exception as e:  # noqa: BLE001
        return print(f"ERR {label}: {e}")
    if isinstance(j, list):
        desc = [{"player": x.get("player"), "chart": x.get("chart"),
                 "score": x.get("score"), "std": x.get("std")} for x in j[:4]]
        print(f"{r.status_code} n={len(j)} {label}\n      {json.dumps(desc, ensure_ascii=False)}")
    else:
        print(f"{r.status_code} {label} :: {r.text[:100]}")


probe("no-token  self", bare, f"/record?player={U}&chart=44231")
probe("with-token self", auth, f"/record?player={U}&chart=44231")
probe("with-token other(2146674)", auth, f"/record?player=2146674&chart=44231")
probe("no-token other(2146674)", bare, f"/record?player=2146674&chart=44231")
probe("multi comma", auth, f"/record?player={U}&chart=44231,13")
probe("multi repeated", auth, f"/record?player={U}&chart=44231&chart=13")
probe("charts=", auth, f"/record?player={U}&charts=44231,13")
probe("unplayed chart", auth, f"/record?player={U}&chart=1")

b = auth.get(f"{H}/record/best/44231", timeout=30).json()
print("best/44231 =", b)
