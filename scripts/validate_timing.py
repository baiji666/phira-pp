"""Validate derived note timing across cached charts.

Reports the distribution of chart span (seconds between first and last note) and
flags charts whose derived timing is implausible, which would indicate that
sentinel BPM values corrupt the beat->seconds mapping.
"""

import glob
import zipfile

import numpy as np

from phira_pp.loader import load_package


def main():
    spans = []
    suspects = []
    formats = {}
    for path in sorted(glob.glob("data/packages/*.bin")):
        with open(path, "rb") as fh:
            blob = fh.read()
        try:
            chart = load_package(blob)
        except Exception:  # noqa: BLE001
            continue
        formats[chart.chart_format] = formats.get(chart.chart_format, 0) + 1
        notes = chart.playable_notes
        if len(notes) < 2:
            continue
        span = notes[-1].time - notes[0].time
        spans.append(span)
        if span < 20 or span > 1200:
            suspects.append((path, chart.chart_format, len(notes), span, chart.duration))

    spans = np.asarray(spans)
    print("charts:", len(spans), "formats:", formats)
    print(f"span(s): min={spans.min():.2f} p05={np.percentile(spans,5):.1f} "
          f"median={np.median(spans):.1f} p95={np.percentile(spans,95):.1f} max={spans.max():.1f}")
    for name, fmt in (("span<20s", lambda x: x < 20), ("span>1200s", lambda x: x > 1200)):
        n = int(fmt(spans).sum()) if len(spans) else 0
        print(f"  {name}: {n}")
    print("suspects:")
    for s in suspects[:15]:
        print(f"  {s[0]} {s[1]} notes={s[2]} span={s[3]:.2f}s duration={s[4]:.2f}s")


if __name__ == "__main__":
    main()
