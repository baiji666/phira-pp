"""Dig for the exact /login payload: enum variants + field-name literals.

Dart AOT stores non-ASCII literals as UTF-16, so CJK UI labels are searched in
both UTF-8 and UTF-16LE.
"""

import re
import zipfile

zf = zipfile.ZipFile("SuonasiOS-0.8.5+46.apk")
data = zf.read("lib/arm64-v8a/libapp.so")


def ctx(i: int, w: int = 120) -> str:
    chunk = data[max(0, i - w):i + w]
    s = re.sub(rb"[^\x20-\x7e]", b" ", chunk).decode("latin-1")
    return re.sub(r"\s{2,}", " ", s).strip()


print("========== CJK labels (utf-8 / utf-16le) ==========")
for word in ("登录", "登入", "密码", "邮箱", "令牌", "账号", "验证码", "注册", "粘贴", "输入",
             "用户名", "邮箱地址"):
    for enc, tag in (("utf-8", "utf8"), ("utf-16-le", "utf16")):
        try:
            b = word.encode(enc)
        except Exception:  # noqa: BLE001
            continue
        hits = [m.start() for m in re.finditer(re.escape(b), data)]
        if hits:
            print(f"\n{word!r} [{tag}] {len(hits)} hits")
            for i in hits[:3]:
                print("   ", ctx(i))

print("\n========== ASCII candidates ==========")
for key in ("LoginP", "LoginPayload", "passwd", "pwd", "phiraId", "userId",
            "user_id", "userName", "username", "session", "auth_session",
            "Bearer ", "captcha", "turnstile", "totp", "code"):
    hits = [m.start() for m in re.finditer(re.escape(key.encode()), data)]
    print(f"\n{key!r}: {len(hits)} hits")
    for i in hits[:4]:
        print("   ", ctx(i, 90))
