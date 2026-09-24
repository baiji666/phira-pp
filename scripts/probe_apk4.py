"""Confirm (a) the machine-readable 定数表 and (b) the login/auth mechanism."""

import re
import zipfile

import requests

S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0"

# ---- (a) the authoritative difficulty table -------------------------------
url = "https://suonasi.07210700.xyz/kv/diff"
r = S.get(url, timeout=30)
print(f"/kv/diff -> {r.status_code} len={len(r.content)}")
lines = [ln for ln in r.text.splitlines() if ln.strip() and not ln.startswith("#")]
print("header:", lines[0])
print("data rows:", len(lines) - 1)
print("first 3:", lines[1:4])
from pathlib import Path
Path("data").mkdir(exist_ok=True)
Path("data/suonasi_diff.tsv").write_text(r.text, "utf-8")
print("saved -> data/suonasi_diff.tsv")

# ---- (b) login / auth strings in the Dart AOT image ----------------------
zf = zipfile.ZipFile("SuonasiOS-0.8.5+46.apk")
data = zf.read("lib/arm64-v8a/libapp.so")


def show(needle: bytes, window: int = 150, limit: int = 5):
    print(f"\n===== {needle!r}")
    n = 0
    for m in re.finditer(re.escape(needle), data):
        i = m.start()
        chunk = data[max(0, i - window):i + window]
        s = re.sub(rb"[^\x20-\x7e]", b" ", chunk).decode("latin-1")
        print("  ", re.sub(r"\s{2,}", " ", s).strip()[:320])
        n += 1
        if n >= limit:
            break


for needle in (b"password", b"email", b"Bearer ", b"Authorization", b"login",
               b"/me", b"token:", b"refresh"):
    hits = len(re.findall(re.escape(needle), data))
    print(f"{needle!r}: {hits} hits")
    if 0 < hits <= 40:
        show(needle, limit=3)
