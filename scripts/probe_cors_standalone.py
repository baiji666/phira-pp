"""Can a browser call the Phira API directly (CORS)?  Decides whether a single
self-contained HTML file is even possible.
"""

import requests

S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0"

HOSTS = ("https://phira.5wyxi.com", "https://api.phira.cn")
ORIGINS = ("http://localhost:8000", "null", "https://example.com")


def get_probe(url, origin):
    r = S.get(url, headers={"Origin": origin}, timeout=30)
    return (r.status_code, r.headers.get("Access-Control-Allow-Origin"),
            r.headers.get("Access-Control-Allow-Credentials"))


print("== simple GET (preflight-free) ==")
for host in HOSTS:
    for path in ("/record?player=0&chart=16593", "/chart/multi-get?ids=51,13", "/user/0"):
        for origin in ORIGINS:
            st, acao, acac = get_probe(host + path, origin)
            print(f"  {host.split('//')[1]:<20} {path:<38} origin={origin:<22} "
                  f"status={st} ACAO={acao!r} ACAC={acac!r}")

print("\n== OPTIONS preflight for POST /login ==")
for host in HOSTS:
    for origin in ORIGINS:
        r = S.options(f"{host}/login", headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        }, timeout=30)
        print(f"  {host.split('//')[1]:<20} origin={origin:<22} status={r.status_code} "
              f"ACAO={r.headers.get('Access-Control-Allow-Origin')!r} "
              f"ACAM={r.headers.get('Access-Control-Allow-Methods')!r} "
              f"ACAH={r.headers.get('Access-Control-Allow-Headers')!r}")

print("\n== POST /login itself (with Origin) ==")
for host in HOSTS:
    r = S.post(f"{host}/login", headers={"Origin": "null"},
               json={"email": "x@example.com", "password": "y"}, timeout=30)
    print(f"  {host.split('//')[1]:<20} status={r.status_code} "
          f"ACAO={r.headers.get('Access-Control-Allow-Origin')!r} body={r.text[:60]!r}")
