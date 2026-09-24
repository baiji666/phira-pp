r"""Start the local web UI for D*/PP.

    .\.venv\Scripts\python.exe scripts\serve.py --port 8000

The browser is opened automatically once the port is bound.  Stop the server by
typing ``off`` + Enter in this console (no y/n prompt).
"""

import argparse
import socket
import sys
import threading
import webbrowser

from phira_pp.webapp import make_server

STOP_WORD = "off"


def _already_listening(host: str, port: int) -> bool:
    """True if something already accepts connections on host:port.

    Windows lets a second ``bind`` succeed on an in-use port (SO_REUSEADDR), so
    an explicit probe is the reliable way to catch a leftover server.
    """
    probe_host = "127.0.0.1" if host in ("", "0.0.0.0") else host
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.6)
            return sock.connect_ex((probe_host, port)) == 0
    except OSError:
        return False


def _watch_stdin(httpd, stop_word=STOP_WORD):
    """Shut the server down as soon as the user types the stop word."""
    for line in sys.stdin:
        if line.strip().lower() == stop_word:
            print("收到 off，正在关闭服务 ...")
            httpd.shutdown()
            return


def main() -> int:
    ap = argparse.ArgumentParser(description="Phira PP local web UI")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    args = ap.parse_args()

    if _already_listening(args.host, args.port):
        print(f"启动失败：端口 {args.port} 已有服务在监听。")
        print("可能是上一次的服务还没关闭——回到那个窗口输入 off 回车即可；")
        print(f"或改用其它端口：start.bat --port {args.port + 1}")
        return 1

    try:
        httpd = make_server(port=args.port, host=args.host)
    except OSError as exc:
        print(f"启动失败：{type(exc).__name__}: {exc}")
        print(f"端口 {args.port} 可能已被占用（是否已有一个服务在运行？）。")
        print(f"可改用其它端口：start.bat --port {args.port + 1}")
        return 1

    url = f"http://{args.host}:{args.port}/"
    print(f"Phira PP web UI -> {url}")
    print("关闭：在本窗口输入 off 并回车（无需确认）。")

    if not args.no_open:
        try:  # the socket is already bound, so the page is reachable right now
            webbrowser.open(url)
        except Exception as exc:  # noqa: BLE001 - opening a browser is best-effort
            print(f"（未能自动打开浏览器：{type(exc).__name__}，请手动访问上面的地址）")

    threading.Thread(target=_watch_stdin, args=(httpd,), daemon=True).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    print("已关闭。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
