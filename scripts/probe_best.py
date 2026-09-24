"""Probe the /record/best/ endpoint family found in SuonasiOS's Dart strings."""

import json

import requests

S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0"

HOSTS = ["https://phira.5wyxi.com", "https://api.phira.cn"]
USER = 0

CANDIDATES = [
    "/record/best/{u}",
    "/record/best/{u}?page=1&pageNum=30",
    "/record/best?user={u}",
    "/record/best?player={u}",
    "/user/{u}/best",
    "/record/query/{u}",
    "/user/{u}/records",
]

for host in HOSTS:
    print(f"\n########## {host}")
    for tpl in CANDIDATES:
        url = host + tpl.format(u=USER)
        try:
            r = S.get(url, timeout=40)
        except Exception as exc:  # noqa: BLE001
            print(f"  {tpl:44s} ERR {type(exc).__name__}")
            continue
        body = r.text[:300].replace("\n", " ")
        print(f"  {tpl:44s} {r.status_code} len={len(r.content):7d} {r.headers.get('content-type','')[:30]}")
        print(f"      {body}")
