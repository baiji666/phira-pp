"""Discover the /login body shape by sending obviously-invalid credentials and
reading the server's discriminator message.

This is payload-shape discovery only (8 tiny requests, no real credentials, no
brute force): a wrong shape answers "did not match any variant of ... LoginP",
a right shape answers something about the account instead.
"""

import requests

S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0"
HOST = "https://phira.5wyxi.com"
BAD = "nobody@example.invalid"

SHAPES = [
    {"account": BAD, "password": "x"},
    {"email": BAD, "password": "x", "totp": ""},
    {"email": BAD, "password": "x", "captcha": ""},
    {"id": 0, "password": "x"},
    {"phiraId": "0", "password": "x"},
    {"user": {"email": BAD, "password": "x"}},
    {"username": BAD, "password": "x"},
    {"email": BAD, "password": "x", "code": ""},
]

for body in SHAPES:
    try:
        r = S.post(f"{HOST}/login", json=body, timeout=25)
    except Exception as exc:  # noqa: BLE001
        print(f"{str(body)[:52]:54s} ERR {type(exc).__name__}")
        continue
    text = r.text[:150].replace("\n", " ")
    matched = "did not match any variant" in text
    print(f"{str(body)[:52]:54s} {r.status_code}  {'SHAPE-REJECTED' if matched else '*** SHAPE ACCEPTED ***'}")
    print(f"     {text}")

# A raw string body is also worth one shot (the app might send form data).
r = S.post(f"{HOST}/login", data={"email": BAD, "password": "x"}, timeout=25)
print(f"\nform-encoded: {r.status_code} {r.text[:150]}")
