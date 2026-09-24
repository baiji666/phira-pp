"""Core data model for Phira charts and play records."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class NoteType(IntEnum):
    """Canonical note types, normalised across all chart formats."""

    TAP = 1
    HOLD = 2
    FLICK = 3
    DRAG = 4


@dataclass(slots=True)
class Note:
    """A single playable note in a normalised coordinate system.

    x is expressed relative to the screen centre and normalised so that the
    half width of the playfield is 1.0 (so x is roughly in [-1, 1]).  Times are
    in seconds relative to the beginning of the chart.
    """

    line: int
    time: float
    x: float
    type: NoteType
    hold: float = 0.0
    above: bool = True
    fake: bool = False
    speed: float = 1.0
    width: float = 1.0
    beat: float = 0.0

    @property
    def end_time(self) -> float:
        return self.time + self.hold


@dataclass(slots=True)
class BpmPoint:
    beat: float
    bpm: float


@dataclass
class Chart:
    notes: list[Note] = field(default_factory=list)
    bpm_points: list[BpmPoint] = field(default_factory=list)
    name: str = ""
    chart_format: str = ""
    offset: float = 0.0
    half_width: float = 675.0
    half_height: float = 450.0
    lines: object | None = None

    @property
    def playable_notes(self) -> list[Note]:
        return [n for n in self.notes if not n.fake]

    @property
    def duration(self) -> float:
        if not self.notes:
            return 0.0
        return max(n.end_time for n in self.notes)

    @property
    def note_count(self) -> int:
        return len(self.playable_notes)


@dataclass
class ChartMeta:
    id: int
    name: str
    level: str
    difficulty: float
    charter: str
    composer: str
    ranked: bool
    reviewed: bool
    stable: bool
    rating: float
    rating_count: int
    file_url: str
    division: str = "regular"
    tags: list[str] = field(default_factory=list)


@dataclass
class PlayRecord:
    """A single play, mirroring the Phira ``/record`` payload."""

    id: int
    player: int
    chart: int
    score: int
    accuracy: float
    perfect: int
    good: int
    bad: int
    miss: int
    max_combo: int
    full_combo: bool
    std: float
    std_score: float
    speed: float = 0.0
    mods: int = 0

    @property
    def total_judged(self) -> int:
        return self.perfect + self.good + self.bad + self.miss
