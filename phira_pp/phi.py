"""Phigros "Official" JSON chart parser (the ``.json`` format that predates RPE).

Time units are 1/32 of a beat, i.e. ``60 / 32 / bpm`` seconds.  Note positions
are given as ``positionX`` relative to the line centre with a half width of 9.

This format is rare among Phira community charts (most use RPE or PEC) and is
kept as a best-effort fallback.
"""

from __future__ import annotations

from .beats import BeatClock
from .models import BpmPoint, Chart, Note, NoteType

_HALF_WIDTH = 9.0
_TYPE_MAP = {1: NoteType.TAP, 2: NoteType.DRAG, 3: NoteType.HOLD, 4: NoteType.FLICK}


def parse_phi(data: dict, name: str = "") -> Chart:
    offset = float(data.get("offset", 0.0) or 0.0)
    notes: list[Note] = []
    bpm_points: list[BpmPoint] = []

    for idx, line in enumerate(data.get("judgeLineList", [])):
        bpm = float(line.get("bpm", 120.0) or 120.0)
        bpm_points.append(BpmPoint(0.0, bpm))
        unit = 60.0 / (32.0 * bpm)  # seconds per time unit

        for key, above in (("notesAbove", True), ("notesBelow", False)):
            for raw in line.get(key, []) or []:
                ntype = _TYPE_MAP.get(int(raw.get("type", 1)), NoteType.TAP)
                start = float(raw.get("time", 0.0)) * unit + offset
                hold = float(raw.get("holdTime", 0.0) or 0.0) * unit
                notes.append(
                    Note(
                        line=idx,
                        time=start,
                        x=float(raw.get("positionX", 0.0)) / _HALF_WIDTH,
                        type=ntype,
                        hold=max(0.0, hold),
                        above=above,
                        fake=False,
                        speed=float(raw.get("speed", 1.0) or 1.0),
                    )
                )

    notes.sort(key=lambda n: n.time)
    return Chart(
        notes=notes,
        bpm_points=sorted(bpm_points, key=lambda p: p.beat),
        name=name,
        chart_format="phi",
        offset=offset,
    )
