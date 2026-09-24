"""How does SuonasiOS obtain its token?  Look for the login screen + payload."""

import re
import zipfile

zf = zipfile.ZipFile("SuonasiOS-0.8.5+46.apk")
data = zf.read("lib/arm64-v8a/libapp.so")

PATTERNS = [b"login", b"Login", b"phiraId", b"verify", b"code", b"register",
            b"/me", b"account", b"session", b"jwt", b"api.phira.cn", b"5wyxi"]

for p in PATTERNS:
    hits = [m.start() for m in re.finditer(re.escape(p), data)]
    print(f"\n===== {p!r}  ({len(hits)} hits)")
    shown = 0
    for i in hits:
        chunk = data[max(0, i - 130):i + 130]
        s = re.sub(rb"[^\x20-\x7e]", b" ", chunk).decode("latin-1")
        s = re.sub(r"\s{2,}", " ", s).strip()
        if len(s) < 12:
            continue
        print("   ", s[:250])
        shown += 1
        if shown >= 5:
            break

print("\n\n===== dart source paths mentioning login/auth =====")
for m in re.finditer(rb"package:suonasi_os/[a-z_/]+\.dart", data):
    s = m.group().decode()
    if any(k in s for k in ("login", "auth", "api", "score", "record", "controller")):
        print("   ", s)
