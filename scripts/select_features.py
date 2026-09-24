"""Forward feature selection for the difficulty model, decided by cross-validation.

Starting from the current base features, greedily add the candidate that most
improves 5-fold CV R2 (with the ridge strength re-chosen by CV each time), and
stop when no candidate helps.  Only CV-improving features are adopted.
"""

import sys

import numpy as np

from phira_pp.dataset import Dataset
from phira_pp.difficulty import cross_val_r2
from phira_pp.features import CANDIDATE_FEATURES, FEATURE_NAMES

ALPHAS = (3.0, 10.0, 30.0, 100.0)
SEEDS = (0, 1, 2, 3, 4)
MIN_GAIN = 0.010


def mean_cv(samples, names, alpha):
    """CV R2 averaged over several fold shuffles (robust to split luck)."""
    return float(np.mean([cross_val_r2(samples, alpha=alpha, names=names, seed=s) for s in SEEDS]))


def best_cv(samples, names):
    scores = [(mean_cv(samples, names, a), a) for a in ALPHAS]
    return max(scores)


def main(limit: int = 200):
    ds = Dataset()
    samples, metas, skipped = ds.collect_training(limit)
    print(f"charts={len(samples)} (skipped {skipped})")

    current = list(FEATURE_NAMES)
    cv, alpha = best_cv(samples, current)
    print(f"base ({len(current)} feats): CV R2={cv:.3f} @alpha={alpha}")

    remaining = [c for c in CANDIDATE_FEATURES if c not in current]
    while remaining:
        trials = []
        for cand in remaining:
            trial = current + [cand]
            tcv, ta = best_cv(samples, trial)
            trials.append((tcv, ta, cand))
        trials.sort(reverse=True)
        tcv, ta, cand = trials[0]
        print(f"  try {cand:20s} -> CV R2={tcv:.3f} @alpha={ta}")
        if tcv > cv + MIN_GAIN:
            current.append(cand)
            cv, alpha = tcv, ta
            remaining.remove(cand)
            print(f"  ADOPT {cand}  ->  CV R2={cv:.3f} ({len(current)} feats)")
        else:
            print("  no candidate improves beyond threshold; stop")
            break

    print(f"\nfinal features ({len(current)}): {current}")
    print(f"final CV R2 = {cv:.3f} @alpha={alpha}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 200)
