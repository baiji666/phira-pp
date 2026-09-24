"""Sample a handful of Phira charts and report their chart-file format."""

import io
import zipfile

from phira_pp.api import PhiraClient

IDS = [14728, 26795, 47579, 57246, 37578, 77972, 78514, 77769, 78543, 78556, 51]


def main():
    client = PhiraClient()
    for chart_id in IDS:
        try:
            meta = client.get_chart(chart_id)
            with zipfile.ZipFile(io.BytesIO(client.download_package(meta))) as zf:
                names = zf.namelist()
            cand = [n for n in names if n.lower().endswith((".pec", ".json", ".pbc"))]
            print(chart_id, meta.level, round(meta.difficulty, 1), cand)
        except Exception as exc:  # noqa: BLE001
            print(chart_id, "ERR", type(exc).__name__, exc)


if __name__ == "__main__":
    main()
