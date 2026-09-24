"""Beat / BPM utilities shared by the chart-format parsers."""

from __future__ import annotations

import bisect

from .models import BpmPoint


def parse_beat(value) -> float:
    """Parse an RPE beat ``[a, b, c]`` (== ``a + b/c``) or a plain number."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, (list, tuple)):
        a = float(value[0]) if len(value) > 0 else 0.0
        b = float(value[1]) if len(value) > 1 else 0.0
        c = float(value[2]) if len(value) > 2 else 1.0
        return a + (b / c if c else 0.0)
    raise TypeError(f"cannot parse beat from {value!r}")


class BeatClock:
    """Converts beats to seconds under a piecewise-constant BPM map."""

    def __init__(self, points: list[BpmPoint]):
        points = sorted(points, key=lambda p: p.beat) or [BpmPoint(0.0, 120.0)]
        if points[0].beat > 0.0:
            points.insert(0, BpmPoint(0.0, points[0].bpm))
        self._beats = [p.beat for p in points]
        self._bpms = [p.bpm for p in points]
        self._cum = [0.0]
        for i in range(1, len(points)):
            seg = (self._beats[i] - self._beats[i - 1]) * 60.0 / self._bpms[i - 1]
            self._cum.append(self._cum[-1] + seg)

    def to_seconds(self, beat: float) -> float:
        i = bisect.bisect_right(self._beats, beat) - 1
        if i < 0:
            i = 0
        return self._cum[i] + (beat - self._beats[i]) * 60.0 / self._bpms[i]
