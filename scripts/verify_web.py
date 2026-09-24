"""Verify the local web UI endpoints against a running server."""

import json

import requests

BASE = "http://127.0.0.1:8000"


def get(path, **params):
    r = requests.get(f"{BASE}{path}", params=params or None, timeout=180)
    return r.status_code, r


def main():
    code, r = get("/")
    print(f"GET /                 -> {code} {r.headers.get('content-type')} "
          f"has_title={'Phira PP' in r.text}")

    code, r = get("/api/result", user=0, chart=16593)
    d = r.json()
    print(f"GET /api/result ok    -> {code} ok={d.get('ok')} "
          f"pp={d.get('pp', {}).get('total') if d.get('pp') else None} source={d.get('source')}")
    print("   player:", d.get("player"))
    print("   chart :", {k: d.get("chart", {}).get(k) for k in ("id", "level", "difficulty", "note_count")})
    if d.get("pp"):
        print("   pp    :", d["pp"])

    code, r = get("/api/result", user=0, chart=16593, exp=1.0)
    d = r.json()
    print(f"GET /api/result exp=1 -> {code} pp={d.get('pp', {}).get('total')} "
          f"diff_exp={d.get('pp', {}).get('diff_exp')}")

    code, r = get("/api/result", user=0, chart=26795, max_scan=120)
    d = r.json()
    print(f"GET /api/result 404rec-> {code} ok={d.get('ok')} kind={d.get('kind')}")

    code, r = get("/api/result", user=999999999, chart=16593)
    d = r.json()
    print(f"GET /api/result baduid-> {code} ok={d.get('ok')} kind={d.get('kind')}")

    code, r = get("/api/result", user="abc", chart=16593)
    d = r.json()
    print(f"GET /api/result badreq-> {code} ok={d.get('ok')} kind={d.get('kind')}")


if __name__ == "__main__":
    main()
