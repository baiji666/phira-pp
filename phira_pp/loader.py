"""Load a Phira chart package (zip) into the normalised :class:`Chart` model."""

from __future__ import annotations

import io
import json
import zipfile

from .models import Chart
from .pec import parse_pec


_NON_CHART_JSON = {"extra.json", "info.json"}


def _pick_chart_member(zf: zipfile.ZipFile, names: list[str]) -> str | None:
    """Choose the chart file inside a package.

    Packages can contain more than one JSON (e.g. ``extra.json`` beside the real
    chart), so ``info.yml``'s ``chart:`` field is authoritative; only if that is
    absent do we fall back to an extension scan that skips known non-chart files.
    """
    for name in names:
        if not name.lower().endswith((".yml", ".yaml")):
            continue
        try:
            text = zf.read(name).decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            continue
        for line in text.splitlines():
            if line.strip().lower().startswith("chart:"):
                value = line.split(":", 1)[1].strip().strip("\"'")
                if value and value in names:
                    return value

    for ext in (".pec", ".json", ".pbc"):
        for name in names:
            if name.lower().endswith(ext) and name.lower() not in _NON_CHART_JSON:
                return name
    return None


def parse_chart_bytes(raw: bytes, name: str = "") -> Chart:
    head = raw[:16].lstrip()
    if head.startswith(b"{"):
        return _parse_json_chart(raw, name)
    return parse_pec(raw.decode("utf-8", errors="replace"), name=name)


def _parse_json_chart(raw: bytes, name: str) -> Chart:
    data = json.loads(raw.decode("utf-8", errors="replace"))
    if _looks_like_rpe(data):
        from .rpe import parse_rpe

        return parse_rpe(data, name=name)
    if isinstance(data, dict) and "judgeLineList" in data:
        from .phi import parse_phi

        return parse_phi(data, name=name)
    raise ValueError("unrecognised JSON chart format")


def _looks_like_rpe(data: dict) -> bool:
    if not isinstance(data, dict):
        return False
    if "META" in data or "BPMList" in data:
        return True
    lines = data.get("judgeLineList") or []
    return bool(lines) and "eventLayers" in lines[0]


def load_package(blob: bytes, name: str = "") -> Chart:
    """Parse a Phira chart package (a zip archive) into a :class:`Chart`."""
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        names = zf.namelist()
        member = _pick_chart_member(zf, names)
        if member is None:
            raise ValueError(f"no chart file found in package: {names}")
        raw = zf.read(member)
    chart = parse_chart_bytes(raw, name=name or member)
    chart.chart_format = chart.chart_format or "unknown"
    return chart
