"""RPE judge-line event evaluation.

Transcribed from the reference implementation in the Phira docs
(chart-standard/chart-format/rpe/judgeLine, "事件插值 → Python 示例"), so the
behaviour is taken from a source rather than inferred:

* an event list is sorted by ``startTime``, gaps are bridged with constant
  events carrying the previous end value, and a sentinel event extends to beat
  ``31250000``;
* looking up a value at time ``t`` returns the **first** event whose
  ``[startTime, endTime]`` covers ``t``, otherwise the supplied default;
* ``eventLayers`` are **summed** per property;
* a line's ``father`` position is **added** to its own.

The reference explicitly does not implement ``bezier`` easing; we likewise
ignore it (usage frequency is measured separately).
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass

from .beats import parse_beat
from .easing import get as get_easing

_SENTINEL_BEAT = 31250000.0
_MAX_FATHER_DEPTH = 16


@dataclass(slots=True)
class Event:
    start: float
    end: float
    sv: float
    ev: float
    easing: int

    def value_at(self, t: float) -> float:
        if t == self.start or self.end == self.start:
            return self.sv
        f = get_easing(self.easing)
        return f((t - self.start) / (self.end - self.start)) * (self.ev - self.sv) + self.sv


def _init_events(events: list[Event]) -> None:
    """Bridge gaps and append a sentinel, exactly as the reference does."""
    bridges = []
    for i, e in enumerate(events):
        if i != len(events) - 1:
            nxt = events[i + 1]
            if e.end < nxt.start:
                bridges.append(Event(e.end, nxt.start, e.ev, e.ev, 1))
    events.extend(bridges)
    events.sort(key=lambda x: x.start)
    if events:
        last = events[-1]
        events.append(Event(last.end, _SENTINEL_BEAT, last.ev, last.ev, 1))


def _build(items: list[dict], force_linear: bool = False) -> list[Event]:
    events = [
        Event(
            start=parse_beat(it["startTime"]),
            end=parse_beat(it["endTime"]),
            sv=float(it.get("start", 0.0)),
            ev=float(it.get("end", 0.0)),
            easing=1 if force_linear else it.get("easingType", 1),
        )
        for it in items
    ]
    _init_events(events)
    return events


class EventLayer:
    _PROPS = ("moveXEvents", "moveYEvents", "rotateEvents", "alphaEvents")

    def __init__(self, raw: dict | None):
        raw = raw or {}
        self._events = {p: _build(raw.get(p) or []) for p in self._PROPS}
        self._events["speedEvents"] = _build(raw.get("speedEvents") or [], force_linear=True)
        self._starts = {p: [e.start for e in evs] for p, evs in self._events.items()}

    def value(self, prop: str, beat: float, default: float) -> float:
        evs = self._events.get(prop)
        if not evs:
            return default
        idx = bisect.bisect_right(self._starts[prop], beat) - 1
        if idx >= 0:
            e = evs[idx]
            if e.start <= beat <= e.end:
                return e.value_at(beat)
        for e in evs:  # faithful fallback for overlapping events
            if e.start <= beat <= e.end:
                return e.value_at(beat)
        return default


class RpeLineSet:
    """Evaluates all judge lines of one RPE chart."""

    def __init__(self, lines_raw: list[dict]):
        self._layers: list[list[EventLayer]] = []
        self._father: list[int] = []
        self._attach_ui: list[object] = []
        for raw in lines_raw:
            self._layers.append([EventLayer(l) for l in (raw.get("eventLayers") or [])])
            self._father.append(int(raw.get("father", -1)))
            self._attach_ui.append(raw.get("attachUI", None))

    def __len__(self) -> int:
        return len(self._layers)

    def pos(self, line: int, beat: float, _depth: int = 0) -> tuple[float, float]:
        x = y = 0.0
        for layer in self._layers[line]:
            x += layer.value("moveXEvents", beat, 0.0)
            y += layer.value("moveYEvents", beat, 0.0)
        father = self._father[line]
        if father != -1 and 0 <= father < len(self._layers) and _depth < _MAX_FATHER_DEPTH:
            fx, fy = self.pos(father, beat, _depth + 1)
            x += fx
            y += fy
        return x, y

    def rotate(self, line: int, beat: float) -> float:
        return sum(layer.value("rotateEvents", beat, 0.0) for layer in self._layers[line])

    def alpha(self, line: int, beat: float) -> float:
        default = 0.0 if (beat >= 0.0 or self._attach_ui[line] is not None) else -255.0
        return sum(layer.value("alphaEvents", beat, default) for layer in self._layers[line])
