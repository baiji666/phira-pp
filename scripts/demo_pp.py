"""End-to-end demo: compute D* for a chart and PP for its top records."""

import sys

from phira_pp.api import PhiraClient
from phira_pp.dataset import Dataset, load_model
from phira_pp.features import extract_features
from phira_pp.loader import load_package
from phira_pp.pp import performance_pp


def main(chart_id: int, model_path: str = "data/difficulty_model.json"):
    client = PhiraClient()
    ds = Dataset(client=client)
    model = load_model(model_path)

    meta = client.get_chart(chart_id)
    chart = load_package(ds.get_package(meta), name=meta.name)
    feats = extract_features(chart)
    if feats is None:
        print("chart too small to analyse")
        return
    d_star = model.predict_features(feats)

    print(
        f"#{meta.id} {meta.name} | {meta.level} | 定数={meta.difficulty:.2f} -> D*={d_star:.2f}"
    )
    print(
        f"notes={chart.note_count} duration={chart.duration:.0f}s "
        f"nps_peak={feats['nps_peak']:.2f} aim_p95={feats['aim_p95']:.2f}"
    )

    records = sorted(client.iter_chart_records(chart_id, max_records=20), key=lambda r: -r.score)
    print(f"{'score':>8} {'acc':>7} {'无暇度':>8} {'combo':>6} {'pp':>8}")
    for rec in records[:15]:
        b = performance_pp(d_star, rec)
        print(
            f"{rec.score:>8d} {rec.accuracy * 100:>6.2f}% "
            f"{rec.std * 1000:>6.2f}ms {rec.max_combo:>6d} {b.pp:>8.1f}"
        )


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 26795)
