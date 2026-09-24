"""Inspect the SuonasiOS APK: structure + embedded URLs / API endpoints."""

import collections
import re
import zipfile

APK = "SuonasiOS-0.8.5+46.apk"

zf = zipfile.ZipFile(APK)
names = [n for n in zf.namelist() if not n.endswith("/")]
print(f"{len(names)} members")
ext = collections.Counter(n.rsplit(".", 1)[-1].lower() for n in names if "." in n)
print("by extension:", ext.most_common(15))

for prefix in ("lib/", "assets/", "res/"):
    sel = [n for n in names if n.startswith(prefix)]
    print(f"\n{prefix} ({len(sel)}):")
    for n in sel[:40]:
        print("   ", n, zf.getinfo(n).file_size)

url_re = re.compile(rb"(?:https?://|/api/)[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%\-]{3,120}")
hits = collections.Counter()
per_file = collections.defaultdict(set)
for n in names:
    info = zf.getinfo(n)
    if info.file_size > 80_000_000:
        print(f"(skip huge {n})")
        continue
    try:
        data = zf.read(n)
    except Exception:  # noqa: BLE001
        continue
    for m in url_re.findall(data):
        s = m.decode("latin-1")
        hits[s] += 1
        per_file[n].add(s)

print("\n=== top hosts/paths ===")
for u, c in hits.most_common(70):
    print(f"{c:5d}  {u[:150]}")

print("\n=== files containing '/api/' or 'phira' ===")
for n, s in per_file.items():
    if any(("phira" in x.lower() or "/api/" in x) for x in s):
        print(n, sorted(s)[:12])
