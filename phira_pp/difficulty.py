"""Objective chart difficulty: a calibrated map from chart features to a
unified difficulty number ``D*`` on the same scale as Phira's 定数.

The map is a ridge regression of the charter-declared 定数 on the objective
feature vector.  Because 定数 is charter-authored and noisy, this only serves
as the *initial anchor* (see the design notes); a population/IRT calibration
can later refine ``D*`` using real play records.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .features import FEATURE_NAMES, extract_features
from .models import Chart

_NEG_INF = float("-inf")
_POS_INF = float("inf")


def prepare_features(
    features: dict[str, float],
    names: list[str],
    clip: dict[str, tuple[float, float]] | None = None,
    hinges: dict[str, tuple[str, float]] | None = None,
) -> dict[str, float]:
    """Turn raw (cached) features into exactly what the model consumes.

    Two guards, both measured rather than assumed:

    * ``clip`` bounds every feature to the range seen in training.  Without it a
      single chart extrapolates: #54540 has ``chord_max``=7346 where the whole
      corpus tops out at 170, so z = +736 and D* = 40.5.  Clipping is a no-op for
      any in-range chart, so it cannot perturb the fitted model.
    * ``hinges`` adds a saturating "stamina" term: ``max(0, log_eff - at)``.  The
      labels stop rising with 物量 around ``log_eff`` 3.4 (band means 17.10 →
      17.88 → 17.83 → 18.20 → 17.76), so beyond that point extra notes may cost
      less; the fit decides how much.  A hinge (not a hard cap) keeps the ordering
      among the biggest charts.

    ``names`` must list the source feature before any hinge built from it.
    """
    clip = clip or {}
    hinges = hinges or {}
    out: dict[str, float] = {}
    for n in names:
        if n in hinges:
            src, at = hinges[n]
            out[n] = max(0.0, out[src] - at)
        else:
            lo, hi = clip.get(n, (_NEG_INF, _POS_INF))
            out[n] = min(max(float(features[n]), lo), hi)
    return out


@dataclass
class DifficultyModel:
    names: list[str]
    weights: np.ndarray
    bias: float
    mean: np.ndarray
    std: np.ndarray
    clip: dict[str, tuple[float, float]] = field(default_factory=dict)
    hinges: dict[str, tuple[str, float]] = field(default_factory=dict)

    def predict_vector(self, vec: np.ndarray) -> float:
        z = (vec - self.mean) / self.std
        return float(z @ self.weights + self.bias)

    def predict_features(self, features: dict[str, float]) -> float:
        prepared = prepare_features(features, self.names, self.clip, self.hinges)
        return self.predict_vector(np.asarray([prepared[n] for n in self.names], dtype=float))

    def predict_chart(self, chart: Chart) -> float | None:
        feats = extract_features(chart)
        if feats is None:
            return None
        return self.predict_features(feats)

    def to_dict(self) -> dict:
        return {
            "names": self.names,
            "weights": self.weights.tolist(),
            "bias": self.bias,
            "mean": self.mean.tolist(),
            "std": self.std.tolist(),
            "clip": {k: list(v) for k, v in self.clip.items()},
            "hinges": {k: list(v) for k, v in self.hinges.items()},
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DifficultyModel":
        return cls(
            names=list(d["names"]),
            weights=np.asarray(d["weights"], dtype=float),
            bias=float(d["bias"]),
            mean=np.asarray(d["mean"], dtype=float),
            std=np.asarray(d["std"], dtype=float),
            clip={k: tuple(v) for k, v in (d.get("clip") or {}).items()},
            hinges={k: tuple(v) for k, v in (d.get("hinges") or {}).items()},
        )


def fit_difficulty_model(
    samples: list[tuple[dict[str, float], float]],
    alpha: float = 1.0,
    names: list[str] | None = None,
    clip: dict[str, tuple[float, float]] | None = None,
    hinges: dict[str, tuple[str, float]] | None = None,
) -> DifficultyModel:
    """Ridge-fit 定数 on objective features.

    ``samples`` is a list of ``(feature_dict, difficulty)`` pairs.  ``names``
    selects a subset of features; defaults to all of :data:`FEATURE_NAMES`.
    ``clip`` / ``hinges`` are stored on the model and applied to the training
    features here too, so the fitted coefficients match what prediction sees.
    """
    names = list(names or FEATURE_NAMES)
    if len(samples) < len(names) + 2:
        raise ValueError(f"need more samples ({len(samples)}) than features")
    xs = np.stack([np.asarray([prepare_features(f, names, clip, hinges)[n] for n in names],
                              dtype=float) for f, _ in samples])
    ys = np.asarray([d for _, d in samples], dtype=float)

    mean = xs.mean(axis=0)
    std = xs.std(axis=0)
    std[std < 1e-8] = 1.0
    z = (xs - mean) / std

    # augment with bias column, ridge-regularise weights only
    n, m = z.shape
    a = np.hstack([z, np.ones((n, 1))])
    reg = np.eye(m + 1) * alpha
    reg[m, m] = 0.0
    coef = np.linalg.solve(a.T @ a + reg, a.T @ ys)

    return DifficultyModel(
        names=names,
        weights=coef[:m],
        bias=float(coef[m]),
        mean=mean,
        std=std,
        clip=dict(clip or {}),
        hinges=dict(hinges or {}),
    )


def cross_val_r2(
    samples: list[tuple[dict[str, float], float]],
    alpha: float = 1.0,
    names: list[str] | None = None,
    folds: int = 5,
    seed: int = 0,
) -> float:
    """Mean k-fold cross-validated R² (the honest generalisation estimate)."""
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(samples))
    chunks = np.array_split(idx, folds)
    scores = []
    for k in range(folds):
        test = chunks[k]
        train_idx = np.concatenate([chunks[j] for j in range(folds) if j != k])
        train = [samples[i] for i in train_idx]
        test = [samples[i] for i in test]
        if len(train) < len(names or FEATURE_NAMES) + 2:
            continue
        model = fit_difficulty_model(train, alpha=alpha, names=names)
        pred = np.asarray([model.predict_features(f) for f, _ in test])
        y = np.asarray([d for _, d in test])
        ss_res = float(((pred - y) ** 2).sum())
        ss_tot = float(((y - y.mean()) ** 2).sum())
        if ss_tot > 0:
            scores.append(1.0 - ss_res / ss_tot)
    return float(np.mean(scores)) if scores else float("nan")


def mean_cross_val_r2(
    samples: list[tuple[dict[str, float], float]],
    alpha: float = 1.0,
    names: list[str] | None = None,
    folds: int = 5,
    seeds: tuple[int, ...] = (0, 1, 2, 3, 4),
) -> float:
    """CV R² averaged over several fold shuffles (robust to split luck)."""
    return float(
        np.mean([cross_val_r2(samples, alpha=alpha, names=names, folds=folds, seed=s) for s in seeds])
    )
