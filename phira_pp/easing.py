"""RPE easing functions (``easingType`` 1..29).

The numbering follows the RPE reference table (Phira docs,
chart-standard/chart-format/rpe/extend#easingtype).  The equations are the
canonical Penner easing functions referenced by that table.  ``get`` clamps the
index exactly as the reference implementation does.
"""

from __future__ import annotations

import math

_PI = math.pi
_C1 = 1.70158
_C2 = _C1 * 1.525
_C3 = _C1 + 1.0
_C4 = (2.0 * _PI) / 3.0
_C5 = (2.0 * _PI) / 4.5


def _linear(x: float) -> float:
    return x


def _in_sine(x: float) -> float:
    return 1.0 - math.cos((x * _PI) / 2.0)


def _out_sine(x: float) -> float:
    return math.sin((x * _PI) / 2.0)


def _in_out_sine(x: float) -> float:
    return -(math.cos(_PI * x) - 1.0) / 2.0


def _in_quad(x: float) -> float:
    return x * x


def _out_quad(x: float) -> float:
    return 1.0 - (1.0 - x) * (1.0 - x)


def _in_out_quad(x: float) -> float:
    return 2.0 * x * x if x < 0.5 else 1.0 - pow(-2.0 * x + 2.0, 2.0) / 2.0


def _in_cubic(x: float) -> float:
    return x * x * x


def _out_cubic(x: float) -> float:
    return 1.0 - pow(1.0 - x, 3.0)


def _in_out_cubic(x: float) -> float:
    return 4.0 * x * x * x if x < 0.5 else 1.0 - pow(-2.0 * x + 2.0, 3.0) / 2.0


def _in_quart(x: float) -> float:
    return x * x * x * x


def _out_quart(x: float) -> float:
    return 1.0 - pow(1.0 - x, 4.0)


def _in_out_quart(x: float) -> float:
    return 8.0 * x * x * x * x if x < 0.5 else 1.0 - pow(-2.0 * x + 2.0, 4.0) / 2.0


def _in_quint(x: float) -> float:
    return x * x * x * x * x


def _out_quint(x: float) -> float:
    return 1.0 - pow(1.0 - x, 5.0)


def _in_out_quint(x: float) -> float:
    return 16.0 * x ** 5 if x < 0.5 else 1.0 - pow(-2.0 * x + 2.0, 5.0) / 2.0


def _in_expo(x: float) -> float:
    return 0.0 if x == 0.0 else pow(2.0, 10.0 * x - 10.0)


def _out_expo(x: float) -> float:
    return 1.0 if x == 1.0 else 1.0 - pow(2.0, -10.0 * x)


def _in_out_expo(x: float) -> float:
    if x == 0.0:
        return 0.0
    if x == 1.0:
        return 1.0
    return pow(2.0, 20.0 * x - 10.0) / 2.0 if x < 0.5 else (2.0 - pow(2.0, -20.0 * x + 10.0)) / 2.0


def _in_circ(x: float) -> float:
    return 1.0 - math.sqrt(1.0 - pow(x, 2.0))


def _out_circ(x: float) -> float:
    return math.sqrt(1.0 - pow(x - 1.0, 2.0))


def _in_out_circ(x: float) -> float:
    if x < 0.5:
        return (1.0 - math.sqrt(1.0 - pow(2.0 * x, 2.0))) / 2.0
    return (math.sqrt(1.0 - pow(-2.0 * x + 2.0, 2.0)) + 1.0) / 2.0


def _in_back(x: float) -> float:
    return _C3 * x * x * x - _C1 * x * x


def _out_back(x: float) -> float:
    return 1.0 + _C3 * pow(x - 1.0, 3.0) + _C1 * pow(x - 1.0, 2.0)


def _in_out_back(x: float) -> float:
    if x < 0.5:
        return (pow(2.0 * x, 2.0) * ((_C2 + 1.0) * 2.0 * x - _C2)) / 2.0
    return (pow(2.0 * x - 2.0, 2.0) * ((_C2 + 1.0) * (x * 2.0 - 2.0) + _C2) + 2.0) / 2.0


def _in_elastic(x: float) -> float:
    if x == 0.0:
        return 0.0
    if x == 1.0:
        return 1.0
    return -pow(2.0, 10.0 * x - 10.0) * math.sin((x * 10.0 - 10.75) * _C4)


def _out_elastic(x: float) -> float:
    if x == 0.0:
        return 0.0
    if x == 1.0:
        return 1.0
    return pow(2.0, -10.0 * x) * math.sin((x * 10.0 - 0.75) * _C4) + 1.0


def _in_out_elastic(x: float) -> float:
    if x == 0.0:
        return 0.0
    if x == 1.0:
        return 1.0
    if x < 0.5:
        return -(pow(2.0, 20.0 * x - 10.0) * math.sin((20.0 * x - 11.125) * _C5)) / 2.0
    return (pow(2.0, -20.0 * x + 10.0) * math.sin((20.0 * x - 11.125) * _C5)) / 2.0 + 1.0


def _out_bounce(x: float) -> float:
    n1, d1 = 7.5625, 2.75
    if x < 1.0 / d1:
        return n1 * x * x
    if x < 2.0 / d1:
        x -= 1.5 / d1
        return n1 * x * x + 0.75
    if x < 2.5 / d1:
        x -= 2.25 / d1
        return n1 * x * x + 0.9375
    x -= 2.625 / d1
    return n1 * x * x + 0.984375


def _in_bounce(x: float) -> float:
    return 1.0 - _out_bounce(1.0 - x)


def _in_out_bounce(x: float) -> float:
    if x < 0.5:
        return (1.0 - _out_bounce(1.0 - 2.0 * x)) / 2.0
    return (1.0 + _out_bounce(2.0 * x - 1.0)) / 2.0


# Index i corresponds to ``easingType == i + 1``.
EASINGS = [
    _linear,            # 1
    _out_sine,          # 2
    _in_sine,           # 3
    _out_quad,          # 4
    _in_quad,           # 5
    _in_out_sine,       # 6
    _in_out_quad,       # 7
    _out_cubic,         # 8
    _in_cubic,          # 9
    _out_quart,         # 10
    _in_quart,          # 11
    _in_out_cubic,      # 12
    _in_out_quart,      # 13
    _out_quint,         # 14
    _in_quint,          # 15
    _out_expo,          # 16
    _in_expo,           # 17
    _out_circ,          # 18
    _in_circ,           # 19
    _out_back,          # 20
    _in_back,           # 21
    _in_out_circ,       # 22
    _in_out_back,       # 23
    _out_elastic,       # 24
    _in_elastic,        # 25
    _out_bounce,        # 26
    _in_bounce,         # 27
    _in_out_bounce,     # 28
    _in_out_elastic,    # 29
]


def get(easing_type: int):
    """Return the easing function for a 1-based ``easingType`` (clamped)."""
    if not isinstance(easing_type, int):
        easing_type = 1
    if easing_type < 1:
        easing_type = 1
    elif easing_type > len(EASINGS):
        easing_type = len(EASINGS)
    return EASINGS[easing_type - 1]
