"""Local web UI for the D*/PP engine.

Stdlib-only HTTP server (no extra dependency) that serves a single HTML page and
a JSON endpoint.  All chart parsing / D* / PP work is delegated to
:class:`~phira_pp.pipeline.PPEngine`, which is shared across requests through a
lock (the underlying Dataset writes to disk).

Run:  python scripts/serve.py [--port 8000]
"""

from __future__ import annotations

import dataclasses
import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

from .api import TOKEN_FILE, load_session, save_session
from .api import login as api_login
from .pipeline import OSU_DECAY, PPEngine, osu_total_pp
from .pp import performance_pp

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

# Static fonts are served from ``/fonts/<name>``; the file may sit in ``web/`` or
# in the project root (where the user dropped ``cmdysj.ttf``).
FONT_DIRS = (WEB_DIR, WEB_DIR.parent)
FONT_EXTS = {".ttf": "font/ttf", ".otf": "font/otf",
             ".woff": "font/woff", ".woff2": "font/woff2"}


def _resolve_font(name: str) -> tuple[Path, str] | None:
    """Map a bare font filename to ``(path, content-type)``; reject anything else."""
    if not name or Path(name).name != name:  # no path separators / traversal
        return None
    ctype = FONT_EXTS.get(Path(name).suffix.lower())
    if ctype is None:
        return None
    for base in FONT_DIRS:
        candidate = base / name
        if candidate.is_file():
            return candidate, ctype
    return None


def _round(x, n=4):
    return None if x is None else round(float(x), n)


def build_result(
    engine: PPEngine, user_id: int, chart_id: int, max_scan: int, exp: float | None = None
) -> tuple[int, dict]:
    """Return ``(http_status, payload)`` for one (player, chart) query."""
    try:
        user = engine.client.get_user(user_id)
    except Exception:  # noqa: BLE001
        return 404, {"ok": False, "error": f"找不到玩家 ID {user_id}", "kind": "player_not_found"}

    try:
        chart = engine.chart(chart_id)
    except Exception:  # noqa: BLE001
        return 404, {"ok": False, "error": f"找不到谱面 #{chart_id}", "kind": "chart_not_found"}

    try:
        result, source = engine.player_chart_play(user_id, chart_id, max_scan=max_scan)
    except Exception as exc:  # noqa: BLE001
        return 502, {"ok": False, "error": f"上游请求失败：{type(exc).__name__}", "kind": "upstream"}

    player = {"id": user.get("id"), "name": user.get("name"), "rks": _round(user.get("rks"), 3)}
    chart_info = {
        "id": chart.meta.id,
        "name": chart.meta.name,
        "level": chart.meta.level,
        "charter": chart.meta.charter,
        "difficulty": _round(chart.meta.difficulty, 2),
        "note_count": chart.note_count,
        "ranked": chart.meta.ranked,
        "d_star": _round(chart.d_star, 2),
        "difficulty_used": _round(chart.difficulty, 2),
        "difficulty_source": chart.difficulty_source,
    }

    if result is None:
        if source == "error":
            return 502, {"ok": False, "kind": "upstream", "player": player,
                         "chart": chart_info, "error": f"查询谱面 #{chart_id} 成绩失败"}
        return 200, {
            "ok": False,
            "kind": "record_not_found",
            "player": player,
            "chart": chart_info,
            "error": f"该玩家在谱面 #{chart_id} 上没有成绩（未游玩或未上传）",
            "source": source,
        }

    rec = result.record
    params = engine.params if exp is None else dataclasses.replace(engine.params, diff_exp=exp)
    b = performance_pp(result.difficulty, rec, params) if result.difficulty else None
    return 200, {
        "ok": True,
        "player": player,
        "chart": chart_info,
        "source": source,
        "record": {
            "score": rec.score,
            "accuracy": _round(rec.accuracy, 6),
            "perfect": rec.perfect,
            "good": rec.good,
            "bad": rec.bad,
            "miss": rec.miss,
            "total": rec.total_judged,
            "max_combo": rec.max_combo,
            "full_combo": rec.full_combo,
            "std_ms": _round(rec.std * 1000.0, 2),
        },
        "pp": None if b is None else {
            "total": _round(b.pp, 1),
            "difficulty": _round(b.difficulty, 2),
            "diff_exp": params.diff_exp,
            "ref_pp": params.ref_pp,
            "ref_diff": params.ref_diff,
            "acc_factor": _round(b.acc_factor, 4),
            "precision_factor": _round(b.precision_factor, 4),
            "error_factor": _round(b.error_factor, 4),
        },
    }


def _best_payload(user: dict, results, stats: dict, n: int) -> dict:
    """The Best-N JSON body, shared by the fast scan and the full scan."""
    top = results[:n]
    total = osu_total_pp([p.pp for p in top])
    items = []
    for i, p in enumerate(top, start=1):
        w = OSU_DECAY ** (i - 1)
        items.append({
            "rank": i,
            "pp": _round(p.pp, 1),
            "weight": _round(w, 4),
            "weighted": _round(p.pp * w, 1),
            "chart": {
                "id": p.chart.id, "name": p.chart.name, "level": p.chart.level,
                "difficulty": _round(p.chart.difficulty, 2),
                "difficulty_used": _round(p.difficulty, 2),
                "difficulty_source": p.difficulty_source,
            },
            "record": {
                "score": p.record.score, "accuracy": _round(p.record.accuracy, 6),
                "std_ms": _round(p.record.std * 1000.0, 2), "miss": p.record.miss,
                "total": p.record.total_judged,
            },
        })
    return {
        "ok": True,
        "player": {"id": user.get("id"), "name": user.get("name"),
                   "rks": _round(user.get("rks"), 3)},
        "total_pp": _round(total, 1),
        "count": len(top),
        "decay": OSU_DECAY,
        "stats": stats,
        "items": items,
    }


def build_best(engine: PPEngine, user_id: int, n: int, per_chart: int,
               workers: int, exp: float | None = None) -> tuple[int, dict]:
    """Fast path: the 定数表 chart set only (~10 s)."""
    try:
        user = engine.client.get_user(user_id)
    except Exception:  # noqa: BLE001
        return 404, {"ok": False, "error": f"找不到玩家 ID {user_id}", "kind": "player_not_found"}

    if exp is not None:
        engine.params = dataclasses.replace(engine.params, diff_exp=exp)
    try:
        results, stats = engine.scan_best_plays(user_id, per_chart=per_chart, workers=workers)
    except Exception as exc:  # noqa: BLE001
        return 502, {"ok": False, "error": f"扫描失败：{type(exc).__name__}", "kind": "upstream"}
    return 200, _best_payload(user, results, stats, n)


# -- full-catalogue scans are minutes long, so they run as background jobs ---
_FULL_JOBS: dict[str, dict] = {}
_FULL_LOCK = threading.Lock()
FULL_KEEP = 8


def _prune_jobs() -> None:
    with _FULL_LOCK:
        done = sorted((j for j in _FULL_JOBS.values() if not j["running"]),
                      key=lambda j: j["started"])
        for job in done[:-FULL_KEEP] if len(done) > FULL_KEEP else []:
            _FULL_JOBS.pop(job["id"], None)


def start_full_best(engine: PPEngine, user_id: int, n: int,
                    exp: float | None = None) -> str | None:
    """Start a full-catalogue scan; ``None`` if one is already running."""
    with _FULL_LOCK:
        if any(j["running"] for j in _FULL_JOBS.values()):
            return None
        if exp is not None:
            engine.params = dataclasses.replace(engine.params, diff_exp=exp)
        job_id = uuid.uuid4().hex
        _FULL_JOBS[job_id] = {
            "id": job_id, "running": True, "done": 0, "total": 0,
            "phase": "准备…", "payload": None, "error": None, "started": time.time(),
        }
    threading.Thread(target=_run_full_best, args=(engine, user_id, n, job_id),
                     daemon=True).start()
    return job_id


def _run_full_best(engine: PPEngine, user_id: int, n: int, job_id: str) -> None:
    state = _FULL_JOBS[job_id]

    def progress(done: int, total: int, phase: str) -> None:
        state["done"], state["total"], state["phase"] = done, total, phase

    try:
        with Handler.lock:  # the Dataset writes to disk, so keep scans serialised
            try:
                user = engine.client.get_user(user_id)
            except Exception:  # noqa: BLE001
                state["error"] = f"找不到玩家 ID {user_id}"
                return
            results, stats = engine.best_plays_full(user_id, progress=progress)
            state["payload"] = _best_payload(user, results, stats, n)
    except Exception as exc:  # noqa: BLE001 - surfaced in the job status
        state["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    finally:
        state["running"] = False
        _prune_jobs()


def full_best_status(job_id: str) -> tuple[int, dict]:
    with _FULL_LOCK:
        state = _FULL_JOBS.get(job_id)
        if state is None:
            return 404, {"ok": False, "error": "job 不存在或已过期", "kind": "not_found"}
        return 200, {
            "ok": True, "running": state["running"], "done": state["done"],
            "total": state["total"], "phase": state["phase"],
            "error": state["error"], "result": state["payload"],
        }


def _session_payload(engine: PPEngine, session: dict) -> dict:
    """Public view of a login session: account id/name/expiry, never the token."""
    sid = session.get("id")
    if sid is None and engine.client.token:
        try:  # token-only files: resolve the owner via /me, then remember it
            sid = engine.client.get_me().get("id")
            if sid is not None:
                session["id"] = sid
        except Exception:  # noqa: BLE001 - stays unknown, never fatal
            sid = None
    name = None
    if sid is not None:
        try:
            name = engine.client.get_user(int(sid)).get("name")
        except Exception:  # noqa: BLE001 - the name is cosmetic
            name = None
    return {"logged_in": True, "id": sid, "name": name, "expire_at": session.get("expireAt")}


def session_status(engine: PPEngine) -> tuple[int, dict]:
    """Current login state (the token itself is never sent to the browser)."""
    session = load_session()
    if not session.get("token"):
        return 200, {"ok": True, "logged_in": False}
    return 200, {"ok": True, **_session_payload(engine, session)}


def do_login(engine: PPEngine, email: str, password: str) -> tuple[int, dict]:
    """Log in via Phira ``/login`` and persist the token.

    The password is only forwarded to Phira and never echoed, logged or stored.
    """
    if not email or not password:
        return 400, {"ok": False, "error": "邮箱和密码不能为空", "kind": "bad_request"}
    try:
        data = api_login(email, password)
    except requests.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else 0
        if code in (400, 401, 403):
            return 401, {"ok": False, "error": "邮箱或密码错误", "kind": "bad_credentials"}
        return 502, {"ok": False, "error": f"登录失败：HTTP {code}", "kind": "upstream"}
    except Exception as exc:  # noqa: BLE001
        return 502, {"ok": False, "error": f"登录请求失败：{type(exc).__name__}", "kind": "upstream"}

    session = save_session(data)
    if not session:
        return 502, {"ok": False, "error": "登录响应中没有 token", "kind": "upstream"}
    engine.client.token = session["token"]
    return 200, {"ok": True, **_session_payload(engine, session)}


def do_logout(engine: PPEngine) -> tuple[int, dict]:
    """Drop the saved token (``data/.token``)."""
    path = Path(TOKEN_FILE)
    if path.exists():
        try:
            path.unlink()
        except OSError as exc:  # noqa: BLE001
            return 500, {"ok": False, "error": f"删除 token 失败：{type(exc).__name__}",
                         "kind": "local"}
    engine.client.token = None
    return 200, {"ok": True, "logged_in": False}


class Handler(BaseHTTPRequestHandler):
    engine: PPEngine
    lock = threading.Lock()
    server_version = "PhiraPP/1.0"

    def log_message(self, fmt, *args):  # keep the console quiet
        pass

    def _send(self, status: int, body: bytes, ctype: str, cache: str = "no-store"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, payload: dict):
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self):  # noqa: N802
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            page = WEB_DIR / "index.html"
            if not page.exists():
                self._send(500, b"index.html missing", "text/plain; charset=utf-8")
                return
            self._send(200, page.read_bytes(), "text/html; charset=utf-8")
            return

        if url.path.startswith("/fonts/"):
            found = _resolve_font(url.path[len("/fonts/"):])
            if found is None:
                self._send_json(404, {"ok": False, "error": "font not found",
                                      "kind": "not_found"})
                return
            font_path, ctype = found
            self._send(200, font_path.read_bytes(), ctype, cache="public, max-age=86400")
            return

        if url.path == "/api/result":
            q = parse_qs(url.query)
            try:
                user_id = int(q.get("user", [""])[0])
                chart_id = int(q.get("chart", [""])[0])
            except (ValueError, TypeError):
                self._send_json(400, {"ok": False, "error": "user 与 chart 必须是数字 ID",
                                      "kind": "bad_request"})
                return
            max_scan = min(max(int(q.get("max_scan", ["600"])[0] or 600), 30), 6000)
            exp = None
            exp_raw = q.get("exp", [""])[0]
            if exp_raw:
                try:
                    exp = min(max(float(exp_raw), 0.5), 4.0)
                except ValueError:
                    exp = None
            with self.lock:
                status, payload = build_result(self.engine, user_id, chart_id, max_scan, exp)
            self._send_json(status, payload)
            return

        if url.path == "/api/best100":
            q = parse_qs(url.query)
            try:
                user_id = int(q.get("user", [""])[0])
            except (ValueError, TypeError):
                self._send_json(400, {"ok": False, "error": "user 必须是数字 ID",
                                      "kind": "bad_request"})
                return
            n = min(max(int(q.get("n", ["100"])[0] or 100), 1), 400)
            per_chart = min(max(int(q.get("per_chart", ["30"])[0] or 30), 5), 100)
            workers = min(max(int(q.get("workers", ["32"])[0] or 32), 1), 64)
            exp = None
            exp_raw = q.get("exp", [""])[0]
            if exp_raw:
                try:
                    exp = min(max(float(exp_raw), 0.5), 4.0)
                except ValueError:
                    exp = None
            with self.lock:
                status, payload = build_best(self.engine, user_id, n, per_chart, workers, exp)
            self._send_json(status, payload)
            return

        if url.path == "/api/best100-full":
            job_id = (parse_qs(url.query).get("job", [""])[0] or "").strip()
            if not job_id:
                self._send_json(400, {"ok": False, "error": "缺少 job 参数",
                                      "kind": "bad_request"})
                return
            self._send_json(*full_best_status(job_id))
            return

        if url.path == "/api/session":
            self._send_json(*session_status(self.engine))
            return

        self._send_json(404, {"ok": False, "error": "not found", "kind": "not_found"})

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            length = 0
        raw = self.rfile.read(length) if length > 0 else b""
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:  # noqa: BLE001
            return {}
        return data if isinstance(data, dict) else {}

    def do_POST(self):  # noqa: N802
        url = urlparse(self.path)
        if url.path == "/api/best100-full":
            body = self._read_json()
            try:
                user_id = int(body.get("user"))
            except (TypeError, ValueError):
                self._send_json(400, {"ok": False, "error": "user 必须是数字 ID",
                                      "kind": "bad_request"})
                return
            n = min(max(int(body.get("n") or 100), 1), 400)
            exp = None
            try:
                if body.get("exp") not in (None, ""):
                    exp = min(max(float(body["exp"]), 0.5), 12.0)
            except (TypeError, ValueError):
                exp = None
            job_id = start_full_best(self.engine, user_id, n, exp)
            if job_id is None:
                self._send_json(409, {"ok": False, "error": "已有一个全量扫描在运行",
                                      "kind": "busy"})
                return
            self._send_json(202, {"ok": True, "job": job_id})
            return
        if url.path == "/api/login":
            body = self._read_json()
            status, payload = do_login(
                self.engine,
                str(body.get("email") or "").strip(),
                str(body.get("password") or ""),
            )
            self._send_json(status, payload)
            return
        if url.path == "/api/logout":
            self._send_json(*do_logout(self.engine))
            return
        self._send_json(404, {"ok": False, "error": "not found", "kind": "not_found"})


def make_server(port: int = 8000, host: str = "127.0.0.1",
                engine: PPEngine | None = None) -> ThreadingHTTPServer:
    handler = Handler
    handler.engine = engine or PPEngine()
    return ThreadingHTTPServer((host, port), handler)
