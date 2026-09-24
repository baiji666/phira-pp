"""Per-play performance points (PP).

    PP = base * D*^diff_exp * acc_factor * precision_factor * error_factor

* ``D*`` is the objective chart difficulty (``phira_pp.difficulty``).
* ``acc`` is the primary weight (hit quality: Perfect/Good/Bad/Miss).
* ``无暇度`` (``std``) is a bounded secondary modifier.
* There is deliberately **no** separate length bonus: D* already scales with
  物量/density (the fitted model puts its largest standardised weight, +1.3980, on
  ``log_eff``, which is exactly why it carries a saturating hinge term and clipped
  inputs — see phira_pp.difficulty.prepare_features), so adding one would double count.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import PlayRecord

# 无暇度 values above this are broken measurements, not slow plays: the clean
# play distribution has p90 = 27 ms whereas the raw data contains values of
# ~23 s.  Such records are treated as neutral instead of being scored.
STD_PLAUSIBLE_MAX = 0.2


@dataclass(frozen=True)
class PPParams:
    # Explicit magnitude contract: a clean play on a D* = ref_diff chart with all
    # factors equal to 1 is worth ref_pp.  The multiplicative base is derived
    # from it, so overriding diff_exp does not change the overall magnitude.
    # Magnitude is a pure PRESENTATION choice (no ground truth exists in Phira's
    # data); anchored so a top-difficulty clean play reads as ~4 digits.
    ref_pp: float = 1000.0
    ref_diff: float = 18.0
    # POLICY parameter, not data-derivable: Phira's own rks is *linear* in 定数,
    # so nothing in the data fixes an exponent.  diff_exp > 1 widens the PP gap
    # between difficulties (the reason this exists).  Configurable per request.
    #
    # Raised 2.0 -> 6.0 on request ("单曲 PP 拉不开差距、低难度的给太多").
    # Measured on 459003's 338 real plays (scripts/sweep_diff_exp.py):
    #   exp   b1-b100 gap   b1/b100   17.0@100%   lowest 定数 in top-100
    #   2.0       144        1.165       892            17.00
    #   4.0       185        1.207       796            17.50
    #   6.0       296        1.319       710            18.00
    #   8.0       419        1.431       633            18.00
    # 6.0 is the smallest value whose Best-100 span clearly exceeds 200 and which
    # pushes every sub-18.0 chart out of the list; orderings stay inversion-free.
    diff_exp: float = 6.0
    acc_floor: float = 0.70
    # Raised 2.0 -> 4.0 on request ("97%/98% 的惩罚太小，拉不开差距").
    # Measured on 459003's 338 real plays (scripts/sweep_acc_pow.py, diff_exp=6):
    #   acc     p=2      p=3      p=4      p=5      pow  b1-b100 gap  b1/b100  inv
    #   99%   0.9344   0.9033   0.8732   0.8441     2.0      295.5      1.319    0
    #   98%   0.8711   0.8130   0.7588   0.7082     4.0      308.4      1.370    0
    #   97%   0.8100   0.7290   0.6561   0.5905     5.0      336.8      1.422    0
    # 4.0 lands near osu!'s top-end accuracy sensitivity (-34% at 97%) while the
    # hardness inversions stay at 0 (a 1.0 定数 step still beats a 0.5% acc drop).
    acc_pow: float = 4.0
    # Bounded precision axis, anchored to the empirical 无暇度 distribution
    # (scripts/calibrate_pp.py: 1392 clean records -> p10 = 15.38 ms,
    # p90 = 27.07 ms).  p10 earns +weight/2, p90 earns -weight/2 and values
    # outside saturate, so 无暇度 moves PP by at most ~+-4%.
    #
    # The weight is capped so this *secondary* modifier can never overturn a 1.0
    # 定数 step.  std is itself correlated with difficulty (harder charts -> larger
    # timing error), so a wide swing systematically cancels the difficulty gain.
    # Measured on real data (scripts/sweep_pp_params.py, 338 plays of 459003):
    # at 0.20 an 18.60@99.85% scored *below* a 17.50@100% (pp x0.9617) and there
    # were 2 such inversions.  The bound (19/18)^2 = 1.114 > (1+w/2)/(1-w/2)
    # requires w < 0.108; 0.08 leaves margin and makes the inversions vanish.
    precision_lo: float = 0.01538
    precision_hi: float = 0.02707
    precision_weight: float = 0.08
    error_pow: float = 3.0

    @property
    def base(self) -> float:
        return self.ref_pp / (self.ref_diff ** self.diff_exp)


@dataclass
class PPBreakdown:
    difficulty: float
    acc_factor: float
    precision_factor: float
    error_factor: float
    pp: float


def precision_factor(std: float, params: PPParams) -> float:
    """Bounded precision multiplier from 无暇度 (seconds)."""
    if std <= 0.0 or std > STD_PLAUSIBLE_MAX:
        return 1.0
    span = params.precision_hi - params.precision_lo
    if span <= 0.0:
        return 1.0
    score = (params.precision_hi - std) / span
    score = min(1.0, max(0.0, score))
    return 1.0 + params.precision_weight * (score - 0.5)


def performance_pp(
    difficulty: float, record: PlayRecord, params: PPParams = PPParams()
) -> PPBreakdown:
    acc = record.accuracy

    if acc < params.acc_floor:
        acc_factor = 0.0
    else:
        acc_factor = ((acc - params.acc_floor) / (1.0 - params.acc_floor)) ** params.acc_pow

    total = max(1, record.total_judged)
    error_rate = (record.bad + record.miss) / total
    error_factor = (1.0 - error_rate) ** params.error_pow

    prec_factor = precision_factor(record.std, params) if record.std > 0.0 else 1.0

    pp = (
        params.base
        * (difficulty ** params.diff_exp)
        * acc_factor
        * prec_factor
        * error_factor
    )
    return PPBreakdown(
        difficulty=difficulty,
        acc_factor=acc_factor,
        precision_factor=prec_factor,
        error_factor=error_factor,
        pp=pp,
    )
