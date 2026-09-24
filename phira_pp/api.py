"""Thin client for the (undocumented) Phira HTTP API."""

from __future__ import annotations

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import requests

from .models import ChartMeta, PlayRecord

DEFAULT_BASE = "https://api.phira.cn"
TOKEN_ENV = "PHIRA_TOKEN"
TOKEN_FILE = "data/.token"


def _decode_file(path: Path) -> str | None:
    """Read a text file tolerantly (BOM / UTF-16 from PowerShell / stray NULs)."""
    if not path.exists():
        return None
    raw = path.read_bytes()
    text = None
    for enc in ("utf-8-sig", "utf-16", "utf-8", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    if not text:
        return None
    return text.replace("\x00", "").strip()


def load_session(path: str | Path = TOKEN_FILE) -> dict:
    """The saved auth session ``{token, id, expireAt, refreshToken}``.

    Login (scripts/login.py) writes JSON; a bare token string is also accepted so
    hand-written token files keep working.
    """
    text = _decode_file(Path(path))
    if not text:
        return {}
    if text.startswith("{"):
        try:
            data = json.loads(text)
            if isinstance(data, dict) and isinstance(data.get("token"), str):
                return data
        except Exception:  # noqa: BLE001 - fall back to treating it as a raw token
            pass
    return {"token": text.strip().strip('"').strip("'").strip()}


def load_token(path: str | Path = TOKEN_FILE) -> str | None:
    """Auth token from ``$PHIRA_TOKEN`` or a local file (never logged/printed)."""
    env = os.environ.get(TOKEN_ENV, "").strip()
    if env:
        return env
    token = load_session(path).get("token")
    return token or None


LOGIN_HOST = "https://phira.5wyxi.com"
TOKEN_KEYS = ("token", "jwt", "session", "accessToken", "access_token", "auth", "authToken")


def extract_token(data: Any) -> str | None:
    """Find the auth token inside a ``/login`` response (any nesting depth)."""
    if isinstance(data, dict):
        for key in TOKEN_KEYS:
            val = data.get(key)
            if isinstance(val, str) and val:
                return val
        for val in data.values():
            token = extract_token(val)
            if token:
                return token
    return None


def login(email: str, password: str, host: str = LOGIN_HOST) -> dict:
    """POST ``/login`` with ``{"email","password"}`` and return the raw JSON.

    The payload shape was confirmed against the live endpoint by shape probing
    (a wrong shape answers "did not match any variant of untagged enum LoginP").
    Credentials go only to Phira's own ``/login`` and are never logged.
    """
    resp = requests.post(
        f"{host.rstrip('/')}/login", json={"email": email, "password": password},
        timeout=30, headers={"User-Agent": "Mozilla/5.0"},
    )
    resp.raise_for_status()
    return resp.json()


def save_session(data: dict, path: str | Path = TOKEN_FILE) -> dict:
    """Persist the ``{token,id,expireAt,refreshToken}`` subset to ``path``.

    Returns the saved session, or ``{}`` if the response carried no token.
    """
    token = extract_token(data)
    if not token:
        return {}
    session = {k: data.get(k) for k in ("token", "id", "expireAt", "refreshToken") if data.get(k)}
    session["token"] = token
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(session, ensure_ascii=False), encoding="utf-8")
    return session


class PhiraClient:
    def __init__(self, base: str = DEFAULT_BASE, timeout: float = 60.0,
                 token: str | None = None):
        self.base = base.rstrip("/")
        self.timeout = timeout
        self.token = token or None
        self._local = threading.local()

    @property
    def session(self) -> requests.Session:
        """One ``requests.Session`` per thread (safe for concurrent scanning)."""
        sess = getattr(self._local, "session", None)
        if sess is None:
            sess = requests.Session()
            if self.token:
                sess.headers["Authorization"] = f"Bearer {self.token}"
            self._local.session = sess
        return sess

    def _get(self, path: str, **params: Any) -> Any:
        resp = self.session.get(f"{self.base}{path}", params=params or None, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    # -- charts ---------------------------------------------------------
    def search_charts(self, **params: Any) -> dict:
        return self._get("/chart", **params)

    def get_chart(self, chart_id: int) -> ChartMeta:
        d = self._get(f"/chart/{chart_id}")
        return _meta_from_dict(d)

    def get_charts(self, ids: list[int]) -> list[ChartMeta]:
        """Metadata for many charts, in parallel 100-id ``multi-get`` chunks."""
        chunks = [ids[i:i + 100] for i in range(0, len(ids), 100)]

        def fetch(chunk: list[int]) -> list[ChartMeta]:
            d = self._get("/chart/multi-get", ids=",".join(str(x) for x in chunk))
            return [_meta_from_dict(x) for x in d]

        if len(chunks) <= 1:
            return fetch(chunks[0]) if chunks else []
        with ThreadPoolExecutor(max_workers=min(8, len(chunks))) as ex:
            parts = list(ex.map(fetch, chunks))
        return [m for part in parts for m in part]

    def download_package(self, meta: ChartMeta | str) -> bytes:
        url = meta.file_url if isinstance(meta, ChartMeta) else meta
        resp = self.session.get(url, timeout=max(self.timeout, 180.0))
        resp.raise_for_status()
        return resp.content

    # -- records --------------------------------------------------------
    def get_record(self, record_id: int) -> PlayRecord:
        return _record_from_dict(self._get(f"/record/{record_id}"))

    def get_records(self, record_ids: list[int]) -> list[PlayRecord]:
        """Batch-fetch records by id via ``/record/multi-get``.

        The endpoint takes ``ids`` as a comma-separated string (repeated query
        keys are rejected with 500).
        """
        out: list[PlayRecord] = []
        for i in range(0, len(record_ids), 100):
            chunk = record_ids[i:i + 100]
            data = self._get("/record/multi-get", ids=",".join(str(x) for x in chunk))
            out.extend(_record_from_dict(x) for x in _extract_rows(data))
        return out

    def query_records(self, chart_id: int, page: int = 1, page_num: int = 30) -> dict:
        """Return the raw ``{"count", ...}`` payload for a chart's records."""
        return self._get(f"/record/query/{chart_id}", page=page, pageNum=page_num)

    def get_me(self) -> dict:
        """The account the current token belongs to (``/me``)."""
        return self._get("/me")

    def get_record_best(self, chart_id: int, **params: Any) -> Any:
        """Raw ``/record/best/{chart_id}`` payload (requires an auth token).

        NB: the path segment is a **chart** id, not a user id — ``/record/best/``
        gives the *token owner's* best ``{score, accuracy, fullCombo}`` on that
        chart (score ``0`` when unplayed).  Verified against real data; passing a
        user id 404s because no such chart exists.
        """
        return self._get(f"/record/best/{chart_id}", **params)

    def query_player_chart(self, user_id: int, chart_id: int) -> list[dict]:
        """A player's record(s) on one chart: ``/record?player=&chart=``.

        This is the real "player x chart" endpoint (found in libapp.so's
        ``fetchBestRecord``).  Verified on real data: it needs **no token**, works
        for **any** player, and its rows always include that account's best
        (flagged ``best: true``) together with ``std`` / 无暇度, so no rank-depth
        blind spot exists.  Returns ``[]`` for an unplayed chart.
        """
        data = self._get("/record", player=user_id, chart=chart_id)
        return data if isinstance(data, list) else _extract_rows(data)

    def iter_chart_records(self, chart_id: int, max_records: int | None = None):
        """Yield :class:`PlayRecord` objects for a chart, following pages."""
        page = 1
        yielded = 0
        while True:
            data = self.query_records(chart_id, page=page)
            rows = _extract_rows(data)
            if not rows:
                break
            for row in rows:
                yield _record_from_dict(row)
                yielded += 1
                if max_records is not None and yielded >= max_records:
                    return
            page += 1

    # -- users ----------------------------------------------------------
    def get_user(self, user_id: int) -> dict:
        return self._get(f"/user/{user_id}")

    def get_best_pool(self, user_id: int) -> dict:
        return self._get(f"/record/get-pool/{user_id}")


def _extract_rows(data: Any) -> list[dict]:
    """Best-effort extraction of the record list from a query response."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list):
                return value
    return []


def _meta_from_dict(d: dict) -> ChartMeta:
    return ChartMeta(
        id=d["id"],
        name=d.get("name") or "",
        level=d.get("level") or "",
        # These three come back as JSON null on some (unrated) catalogue rows, so
        # they must be coerced explicitly — `d.get(k, 0)` does not cover null.
        difficulty=float(d.get("difficulty") or 0.0),
        charter=d.get("charter") or "",
        composer=d.get("composer") or "",
        ranked=bool(d.get("ranked", False)),
        reviewed=bool(d.get("reviewed", False)),
        stable=bool(d.get("stable", False)),
        rating=float(d.get("rating") or 0.0),
        rating_count=int(d.get("ratingCount") or 0),
        file_url=d.get("file") or "",
        division=d.get("division") or "regular",
        tags=list(d.get("tags") or []),
    )


def _record_from_dict(d: dict) -> PlayRecord:
    return PlayRecord(
        id=d["id"],
        player=d["player"],
        chart=d["chart"],
        score=int(d["score"]),
        accuracy=float(d.get("accuracy") or 0.0),
        perfect=int(d.get("perfect") or 0),
        good=int(d.get("good") or 0),
        bad=int(d.get("bad") or 0),
        miss=int(d.get("miss") or 0),
        max_combo=int(d.get("max_combo") or 0),
        full_combo=bool(d.get("full_combo", False)),
        std=float(d.get("std") or 0.0),
        std_score=float(d.get("std_score") or 0.0),
        speed=float(d.get("speed") or 0.0),
        mods=int(d.get("mods") or 0),
    )
