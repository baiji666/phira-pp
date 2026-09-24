"""RPE (Re:PhiEdit) JSON chart parser.

Reference: Phira docs, chart-standard/chart-format/rpe.

Position notes are stored relative to the judging line centre with an X range of
``-675..675``; we normalise by 675 so the playfield half width is 1.0.
"""

from __future__ import annotations

from .beats import BeatClock, parse_beat
from .lineevents import RpeLineSet
from .models import BpmPoint, Chart, Note, NoteType

_HALF_WIDTH = 675.0


def _bpm_points(data: dict) -> list[BpmPoint]:
    raw = data.get("BPMList") or data.get("bpmList") or []
    points = [BpmPoint(parse_beat(p["startTime"]), float(p["bpm"])) for p in raw]
    return points or [BpmPoint(0.0, 120.0)]


def parse_rpe(data: dict, name: str = "") -> Chart:
    points = _bpm_points(data)
    clock = BeatClock(points)

    offset = float(data.get("META", {}).get("offset", 0) or 0) / 1000.0

    notes: list[Note] = []
    lines_raw = data.get("judgeLineList", [])
    for idx, line in enumerate(lines_raw):
        for raw in line.get("notes", []):
            start_beat = parse_beat(raw["startTime"])
            end_beat = parse_beat(raw.get("endTime", raw["startTime"]))
            start = clock.to_seconds(start_beat) + offset
            end = clock.to_seconds(end_beat) + offset
            try:
                ntype = NoteType(int(raw.get("type", 1)))
            except ValueError:
                ntype = NoteType.TAP
            notes.append(
                Note(
                    line=idx,
                    time=start,
                    x=float(raw.get("positionX", 0.0)) / _HALF_WIDTH,
                    type=ntype,
                    hold=max(0.0, end - start),
                    above=int(raw.get("above", 1)) == 1,
                    fake=int(raw.get("isFake", 0)) == 1,
                    speed=float(raw.get("speed", 1.0) or 1.0),
                    width=float(raw.get("size", 1.0) or 1.0),
                    beat=start_beat,
                )
            )

    notes.sort(key=lambda n: n.time)
    return Chart(
        notes=notes,
        bpm_points=sorted(points, key=lambda p: p.beat),
        name=name,
        chart_format="rpe",
        offset=offset,
        half_width=_HALF_WIDTH,
        lines=RpeLineSet(lines_raw),
    )
