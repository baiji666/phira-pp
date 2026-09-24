"""Determine how a token is obtained: probe POST /login for its required fields.

We deliberately send incomplete/blank bodies to read the server's validation
errors instead of guessing the payload.
"""

import json

import requests

S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0"

HOST = "https://phira.5wyxi.com"

for desc, body in (
    ("empty json", {}),
    ("email only", {"email": "x@example.invalid"}),
    ("user/password", {"user": "x", "password": "y"}),
    ("email+code", {"email": "x@example.invalid", "code": "000000"}),
):
    try:
        r = S.post(f"{HOST}/login", json=body, timeout=25)
    except Exception as exc:  # noqa: BLE001
        print(f"{desc:14s} ERR {type(exc).__name__}")
        continue
    print(f"{desc:14s} {r.status_code} {r.text[:220].replace(chr(10), ' ')}")

# Is there a register / code-request endpoint?
for path in ("/register", "/login/email", "/email/code", "/me"):
    try:
        r = S.get(HOST + path, timeout=20)
        print(f"\nGET {path:14s} {r.status_code} {r.text[:160].replace(chr(10), ' ')}")
    except Exception as exc:  # noqa: BLE001
        print(f"\nGET {path:14s} ERR {type(exc).__name__}")

print("\n--- a couple of header diagnostics on /login")
r = S.get(f"{HOST}/login", timeout=20)
print("GET /login:", r.status_code, dict(list(r.headers.items())[:6]))
print(json.dumps({"note": "no credentials were sent anywhere meaningful"}, ensure_ascii=False))
