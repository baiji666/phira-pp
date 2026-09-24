"""Diagnose which feature causes extreme standardised values in CV folds."""

import numpy as np

from phira_pp.dataset import Dataset
from phira_pp.features import FEATURE_NAMES

LIMIT = 120


def main():
    ds = Dataset()
    samples, metas, _ = ds.collect_training(LIMIT)
    xs = np.stack([[f[n] for n in FEATURE_NAMES] for f, _ in samples])
    print("n =", len(samples))
    print(f"{'feature':16s} {'global_std':>12s} {'min':>12s} {'max':>12s}")
    for j, name in enumerate(FEATURE_NAMES):
        col = xs[:, j]
        print(f"{name:16s} {col.std():12.6g} {col.min():12.6g} {col.max():12.6g}")

    rng = np.random.default_rng(0)
    idx = rng.permutation(len(samples))
    chunks = np.array_split(idx, 5)
    for k in range(5):
        train = np.concatenate([chunks[j] for j in range(5) if j != k])
        test = chunks[k]
        tr = xs[train]
        mean, std = tr.mean(axis=0), tr.std(axis=0)
        std[std < 1e-8] = 1.0
        z = (xs[test] - mean) / std
        worst = np.argmax(np.abs(z).max(axis=0))
        print(f"fold {k}: max|z|={np.abs(z).max():.3e} at feature '{FEATURE_NAMES[worst]}' "
              f"train_std={std[worst]:.3e}")


if __name__ == "__main__":
    main()
