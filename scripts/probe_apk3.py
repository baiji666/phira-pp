"""Wider look at SuonasiOS's API usage: full path templates + auth handling."""

import re
import zipfile

zf = zipfile.ZipFile("SuonasiOS-0.8.5+46.apk")
data = zf.read("lib/arm64-v8a/libapp.so")


def show(needle: bytes, window: int = 200, limit: int = 6):
    print(f"\n===== {needle!r}")
    n = 0
    for m in re.finditer(re.escape(needle), data):
        i = m.start()
        chunk = data[max(0, i - window):i + window]
        s = re.sub(rb"[^\x20-\x7e]", b" ", chunk).decode("latin-1")
        s = re.sub(r"\s{2,}", " ", s).strip()
        print(f"  [{i}] {s[:330]}")
        n += 1
        if n >= limit:
            break


for needle in (b"/record/", b"/login", b"/user/", b"/chart/"):
    show(needle)

for needle in (b"Authorization", b"Bearer", b"token", b"auth", b"Cookie", b"signature"):
    hits = len(re.findall(re.escape(needle), data))
    print(f"\n{needle!r}: {hits} hits")

show(b"Authorization", window=160, limit=4)
show(b"Bearer", window=160, limit=4)
show(b"token", window=140, limit=6)

# where does it read the local catalog from?
show(b"diff.tsv", window=120, limit=3)
show(b"catalog", window=120, limit=4)
