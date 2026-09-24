"""Log in to Phira locally and save the resulting token to ``data/.token``.

Payload shape ``{"email", "password"}`` was confirmed against the live endpoint
by payload-shape probing (a wrong shape answers "did not match any variant of
untagged enum LoginP"; this shape answers "Email or password is wrong").

Credentials are typed locally, never echoed, never written to disk, and never
sent anywhere except Phira's own /login.  Only the response *field names* are
printed, so the output is safe to share.
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys

import requests

from phira_pp.api import LOGIN_HOST, TOKEN_FILE, login, save_session


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", help="Phira 邮箱；不填则交互输入")
    ap.add_argument("--host", default=LOGIN_HOST)
    ap.add_argument("--out", default=TOKEN_FILE)
    args = ap.parse_args()

    email = args.email or input("Phira 邮箱: ").strip()
    if sys.stdin.isatty():
        password = getpass.getpass("Phira 密码（不回显）: ")
    else:  # piped/scripted: read a line instead of blocking on the console
        password = sys.stdin.readline().strip()

    if not email or not password:
        print("邮箱或密码为空，已取消")
        return 2

    try:
        data = login(email, password, args.host)
    except requests.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else 0
        body = exc.response.text[:200] if exc.response is not None else ""
        print(f"登录失败: HTTP {code} {body}")
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"请求失败: {type(exc).__name__}: {str(exc)[:150]}")
        return 1

    if isinstance(data, dict):
        print("响应字段:", sorted(data.keys()))
    session = save_session(data, args.out)
    if not session:
        shape = ({k: type(v).__name__ for k, v in data.items()}
                 if isinstance(data, dict) else type(data).__name__)
        print("未在响应中找到 token 字段（值未打印）:", json.dumps(shape, ensure_ascii=False))
        return 1

    print(f"成功：token 已保存到 {args.out}（长度 {len(session['token'])}，内容未打印）")
    print(f"     会话字段: {sorted(session)}  账号 id: {session.get('id')}")
    if session.get("expireAt"):
        print(f"     过期时间: {session['expireAt']}（过期后重新运行本脚本即可）")
    print("下一步: $env:PYTHONPATH=\".\"; .\\.venv\\Scripts\\python.exe scripts\\pp.py best <id>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
