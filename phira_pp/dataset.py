"""Caching dataset helpers: download chart packages once and reuse them.

Handles the batch-collection step needed both for difficulty calibration and
for later population/IRT fitting.
"""

from __future__ import annotations

import json
from pathlib import Path

from .api import PhiraClient
from .difficulty import DifficultyModel
from .features import FEATURE_NAMES, FEATURES_VERSION, extract_features
from .loader import load_package
from .models import ChartMeta

DEFAULT_CACHE = Path("data")


class Dataset:
    def __init__(self, cache_dir: Path | str = DEFAULT_CACHE, client: PhiraClient | None = None):
        self.root = Path(cache_dir)
        self.pkg_dir = self.root / "packages"
        self.feat_dir = self.root / "features"
        self.pkg_dir.mkdir(parents=True, exist_ok=True)
        self.feat_dir.mkdir(parents=True, exist_ok=True)
        self.client = client or PhiraClient()

    # -- raw packages ---------------------------------------------------
    def package_path(self, chart_id: int) -> Path:
        return self.pkg_dir / f"{chart_id}.bin"

    def get_package(self, meta: ChartMeta, refresh: bool = False) -> bytes:
        path = self.package_path(meta.id)
        if path.exists() and not refresh:
            return path.read_bytes()
        blob = self.client.download_package(meta)
        path.write_bytes(blob)
        return blob

    # -- features -------------------------------------------------------
    def features_path(self, chart_id: int) -> Path:
        return self.feat_dir / f"{chart_id}.json"

    def get_features(self, meta: ChartMeta, refresh: bool = False) -> dict | None:
        path = self.features_path(meta.id)
        if path.exists() and not refresh:
            cached = json.loads(path.read_text("utf-8"))
            if cached.get("_version") == FEATURES_VERSION and all(
                k in cached for k in FEATURE_NAMES
            ):
                # A cache hit used to return immediately, so a file that had lost
                # its label could never be repaired -- and nothing told anyone
                # (build_train_set.py's "backfill" was silently a no-op).  Restore
                # the provenance from the meta we were handed and persist it.
                if not isinstance(cached.get("_difficulty"), (int, float)):
                    cached["_difficulty"] = meta.difficulty
                    cached["_ranked"] = bool(meta.ranked)
                    cached["_rating_count"] = int(meta.rating_count)
                    path.write_text(json.dumps(cached), "utf-8")
                return cached
        blob = self.get_package(meta, refresh=refresh)
        try:
            chart = load_package(blob, name=meta.name)
        except Exception:  # noqa: BLE001 - unsupported format, skip gracefully
            return None
        feats = extract_features(chart)
        if feats is not None:
            feats["_format"] = chart.chart_format
            feats["_note_count"] = chart.note_count
            feats["_version"] = FEATURES_VERSION
            # keep the label + provenance alongside the features so the training
            # set can be rebuilt/audited straight from the cache
            feats["_difficulty"] = meta.difficulty
            feats["_ranked"] = bool(meta.ranked)
            feats["_rating_count"] = int(meta.rating_count)
            path.write_text(json.dumps(feats), "utf-8")
        return feats

    # -- fitting on whatever is cached ----------------------------------
    def collect_from_cache(
        self, dmin: float = 1.0, dmax: float = 20.0, min_rating_count: int = 0,
        ranked_only: bool = False,
    ) -> tuple[list[tuple[dict, float]], list[int], int]:
        """Return ``(samples, chart_ids, skipped``) from every cached feature file."""
        samples: list[tuple[dict, float]] = []
        ids: list[int] = []
        skipped = 0
        for path in sorted(self.feat_dir.glob("*.json")):
            try:
                feats = json.loads(path.read_text("utf-8"))
            except Exception:  # noqa: BLE001
                skipped += 1
                continue
            if feats.get("_version") != FEATURES_VERSION or "_difficulty" not in feats:
                skipped += 1
                continue
            if not all(k in feats for k in FEATURE_NAMES):
                skipped += 1
                continue
            d = float(feats["_difficulty"])
            if not (dmin <= d <= dmax):
                skipped += 1
                continue
            if int(feats.get("_rating_count", 0)) < min_rating_count:
                skipped += 1
                continue
            if ranked_only and not feats.get("_ranked"):
                skipped += 1
                continue
            samples.append(({k: feats[k] for k in FEATURE_NAMES}, d))
            ids.append(int(path.stem))
        return samples, ids, skipped

    # -- collection -----------------------------------------------------
    def iter_ranked_metas(self, limit: int, page_num: int = 30, min_rating_count: int = 50):
        """Walk the regular chart listing and yield well-established charts."""
        from .api import _meta_from_dict

        page = 1
        found = 0
        while found < limit:
            data = self.client.search_charts(
                page=page, pageNum=page_num, order="rating", division="regular"
            )
            rows = data.get("results") or data.get("result") or []
            if not rows:
                break
            for row in rows:
                meta = _meta_from_dict(row)
                if not (meta.ranked and meta.reviewed):
                    continue
                if meta.rating_count < min_rating_count or meta.difficulty <= 0:
                    continue
                yield meta
                found += 1
                if found >= limit:
                    return
            page += 1

    def collect_training(self, limit: int, refresh: bool = False):
        """Return ``(samples, metas, skipped)`` for difficulty fitting."""
        samples: list[tuple[dict, float]] = []
        metas: list[ChartMeta] = []
        skipped = 0
        for meta in self.iter_ranked_metas(limit):
            feats = self.get_features(meta, refresh=refresh)
            if feats is None:
                skipped += 1
                continue
            clean = {k: v for k, v in feats.items() if not k.startswith("_")}
            samples.append((clean, meta.difficulty))
            metas.append(meta)
        return samples, metas, skipped


def save_model(model: DifficultyModel, path: Path | str) -> None:
    Path(path).write_text(json.dumps(model.to_dict(), indent=2), "utf-8")


def load_model(path: Path | str) -> DifficultyModel:
    return DifficultyModel.from_dict(json.loads(Path(path).read_text("utf-8")))
