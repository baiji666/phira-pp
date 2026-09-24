"""Parse a Phira chart package and print basic timeline statistics."""

import collections
import sys

from phira_pp import NoteType
from phira_pp.api import PhiraClient
from phira_pp.loader import load_package


def main(chart_id: int):
    client = PhiraClient()
    meta = client.get_chart(chart_id)
    print(f"#{meta.id} {meta.name} | {meta.level} | 定数={meta.difficulty:.2f} | format file={meta.file_url[-12:]}")

    blob = client.download_package(meta)
    chart = load_package(blob, name=meta.name)

    notes = chart.playable_notes
    kinds = collections.Counter(NoteType(n.type).name for n in notes)
    print("format:", chart.chart_format)
    print("notes:", len(notes), "fake:", len(chart.notes) - len(notes))
    print("types:", dict(kinds))
    print("bpm points:", [(round(p.beat, 2), p.bpm) for p in chart.bpm_points[:5]])
    print(f"duration: {chart.duration:.1f}s")
    if notes:
        print(f"first note t={notes[0].time:.3f}s x={notes[0].x:.3f}")
        print(f"last  note t={notes[-1].time:.3f}s x={notes[-1].x:.3f}")
    holds = [n for n in notes if n.type == NoteType.HOLD]
    if holds:
        total_hold = sum(n.hold for n in holds)
        print(f"holds: {len(holds)} total={total_hold:.1f}s mean={total_hold/len(holds):.3f}s")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 51)
