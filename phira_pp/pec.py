"""PEC (PhiEditer Chart) text-format parser.

Grammar reference (from Phira docs, chart-standard/chart-format/pe):

* first non-empty line      -> chart offset in ms (int)
* ``bp <beat> <bpm>``       -> BPM point
* ``n1 <line> <beat> <x> <fromBelow> <fake>``            -> Tap
* ``n2 <line> <beat> <endBeat> <x> <fromBelow> <fake>``  -> Hold
* ``n3 <line> <beat> <x> <fromBelow> <fake>``            -> Flick
* ``n4 <line> <beat> <x> <fromBelow> <fake>``            -> Drag
* ``# <speed>`` / ``& <width>`` -> applies to the previous note
* ``cv/cp/cd/ca`` instant events, ``cm/cr/cf`` easing events

File coordinates use a centre of (1024, 700) with x in [-1024, 1024]; we
normalise x by 1024 so the playfield half width is 1.0.
"""

from __future__ import annotations

from .beats import BeatClock
from .models import BpmPoint, Chart, Note, NoteType

_NOTE_COMMANDS = {"n1": NoteType.TAP, "n2": NoteType.HOLD, "n3": NoteType.FLICK, "n4": NoteType.DRAG}
_HALF_WIDTH = 1024.0


def parse_pec(text: str, name: str = "") -> Chart:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        raise ValueError("empty PEC chart")

    offset = float(lines[0]) / 1000.0

    bpm_points: list[BpmPoint] = []
    raw_notes: list[dict] = []
    last_note: dict | None = None

    for line in lines[1:]:
        head = line.split(maxsplit=1)[0]
        if head == "bp":
            _, beat, bpm = line.split()
            bpm_points.append(BpmPoint(float(beat), float(bpm)))
        elif head in _NOTE_COMMANDS:
            parts = line.split()
            ntype = _NOTE_COMMANDS[head]
            if ntype is NoteType.HOLD:
                _, line_idx, start, end, x, below, fake = parts
                note = {
                    "line": int(line_idx),
                    "start": float(start),
                    "end": float(end),
                    "x": float(x),
                    "type": ntype,
                    "above": below != "2",
                    "fake": fake == "1",
                }
            else:
                _, line_idx, beat, x, below, fake = parts
                note = {
                    "line": int(line_idx),
                    "start": float(beat),
                    "end": float(beat),
                    "x": float(x),
                    "type": ntype,
                    "above": below != "2",
                    "fake": fake == "1",
                }
            note["speed"] = 1.0
            note["width"] = 1.0
            raw_notes.append(note)
            last_note = note
        elif line.startswith("#") and last_note is not None:
            last_note["speed"] = float(line[1:].strip())
        elif line.startswith("&") and last_note is not None:
            last_note["width"] = float(line[1:].strip())
        # every other command describes a judge-line event, ignored for now

    clock = BeatClock(bpm_points)
    notes: list[Note] = []
    for raw in raw_notes:
        start = clock.to_seconds(raw["start"]) + offset
        end = clock.to_seconds(raw["end"]) + offset
        notes.append(
            Note(
                line=raw["line"],
                time=start,
                x=raw["x"] / _HALF_WIDTH,
                type=raw["type"],
                hold=max(0.0, end - start),
                above=raw["above"],
                fake=raw["fake"],
                speed=raw["speed"],
                width=raw["width"],
            )
        )

    notes.sort(key=lambda n: n.time)
    return Chart(
        notes=notes,
        bpm_points=sorted(bpm_points, key=lambda p: p.beat),
        name=name,
        chart_format="pec",
        offset=offset,
        half_width=_HALF_WIDTH,
        half_height=700.0,
    )
