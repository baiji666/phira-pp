"""Collect ranked charts, fit the objective difficulty model, and report fit."""

import sys

import numpy as np

from phira_pp.dataset import Dataset, save_model
from phira_pp.difficulty import fit_difficulty_model, mean_cross_val_r2
from phira_pp.features import FEATURE_NAMES, LINE_FEATURES

ALPHAS = (3.0, 10.0, 30.0, 100.0)


def main(limit: int = 50, alpha: float | None = None, out: str = "data/difficulty_model.json",
         from_cache: bool = False):
    ds = Dataset()
    if from_cache:
        samples, ids, skipped = ds.collect_from_cache()
        metas = None
        print(f"from cache: {len(samples)} samples (skipped {skipped} unusable cached files)")
    else:
        samples, metas, skipped = ds.collect_training(limit)
        ids = None
        print(f"collected {len(samples)} charts (skipped {skipped} unparsable)")
    if len(samples) < len(FEATURE_NAMES) + 2:
        print("not enough samples to fit")
        return

    base_names = list(FEATURE_NAMES)
    with_line = base_names + LINE_FEATURES
    have_line = all(n in samples[0][0] for n in LINE_FEATURES)
    ys_all = np.asarray([d for _, d in samples])
    print(f"定数 range: {ys_all.min():.1f}-{ys_all.max():.1f} "
          f"p10={np.percentile(ys_all,10):.1f} median={np.median(ys_all):.1f} "
          f"p90={np.percentile(ys_all,90):.1f}")
    print("alpha sweep (seed-averaged 5-fold CV R2):")
    best_alpha, best_cv = ALPHAS[0], float("-inf")
    for a in ALPHAS:
        cv_base = mean_cross_val_r2(samples, alpha=a, names=base_names)
        cv_line = (mean_cross_val_r2(samples, alpha=a, names=with_line)
                   if have_line else float("nan"))
        if cv_base > best_cv:
            best_cv, best_alpha = cv_base, a
        print(f"  alpha={a:6.1f}  base={cv_base:+.3f}  with-line={cv_line:+.3f}")
    if alpha is None:
        alpha = best_alpha
    print(f"chosen alpha={alpha} (by CV), CV R2={best_cv:.3f}")

    model = fit_difficulty_model(samples, alpha=alpha)
    preds = np.asarray([model.predict_features(f) for f, _ in samples])
    ys = np.asarray([d for _, d in samples])
    ss_res = float(((preds - ys) ** 2).sum())
    ss_tot = float(((ys - ys.mean()) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot
    rmse = float(np.sqrt(((preds - ys) ** 2).mean()))
    print(f"R2={r2:.3f}  RMSE={rmse:.3f}  (n={len(samples)})")

    print("largest weights (standardised):")
    for name, w in sorted(zip(model.names, model.weights), key=lambda t: -abs(t[1])):
        print(f"  {name:14s} {w:+.3f}")

    print("feature vs 定数 correlation:")
    for name in FEATURE_NAMES:
        col = np.asarray([f[name] for f, _ in samples])
        if col.std() > 0:
            print(f"  {name:16s} r={np.corrcoef(col, ys)[0, 1]:+.3f}")

    save_model(model, out)
    print("saved ->", out)

    print("samples (定数 -> D*):")
    order = np.argsort(ys)
    step = max(1, len(order) // 12)
    for i in order[::step]:
        ident = metas[i].id if metas is not None else (ids[i] if ids else "?")
        lvl = metas[i].level if metas is not None else ""
        print(f"  #{ident} {lvl:16s} 定数={ys[i]:5.1f}  D*={preds[i]:5.2f}")


if __name__ == "__main__":
    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    main(int(argv[0]) if argv else 50, from_cache="--from-cache" in flags)
