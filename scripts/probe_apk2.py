"""Follow the SuonasiOS APK's own endpoints:
  * its KV service (machine-readable 定数表 / 谱师数据)
  * its Phira API host (phira.5wyxi.com)
plus grep libapp.so for the API paths it actually calls.
"""

import json
import re
import zipfile

import requests

S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0"

for path in ("/kv/diff", "/kv/diff_staff", "/kv/staff_list"):
    url = "https://suonasi.07210700.xyz" + path
    try:
        r = S.get(url, timeout=30)
        print(f"\n=== {url} -> {r.status_code} {r.headers.get('content-type')} "
              f"len={len(r.content)}")
        text = r.text
        print(text[:600])
    except Exception as exc:  # noqa: BLE001
        print(f"\n=== {url} ERROR {type(exc).__name__}: {str(exc)[:120]}")

print("\n\n=== libapp.so path strings ===")
zf = zipfile.ZipFile("SuonasiOS-0.8.5+46.apk")
data = zf.read("lib/arm64-v8a/libapp.so")
print("libapp.so bytes:", len(data))

pats = [b"/record", b"/user", b"/chart", b"get-pool", b"pageNum", b"5wyxi",
        b"phira", b"query", b"player", b"suonasi", b"/kv/", b"diff.tsv", b"id="]
for p in pats:
    idx = [m.start() for m in re.finditer(re.escape(p), data)]
    print(f"\n--- {p!r}: {len(idx)} hits")
    seen = set()
    for i in idx[:400]:
        chunk = data[max(0, i - 40):i + 70]
        s = re.sub(rb"[^\x20-\x7e]", b" ", chunk).decode("latin-1").strip()
        s = re.sub(r"\s{2,}", " ", s)
        if s not in seen and len(s) > 6:
            seen.add(s)
            print("     ", s[:120])
        if len(seen) >= 12:
            break
