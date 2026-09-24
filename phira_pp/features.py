"""Objective difficulty features extracted from a parsed chart.

Signals are derived from the chart's note timeline and — when judge-line events
are available — from the real on-screen position of each note.  They do not
depend on the charter's own difficulty claim, so they provide an objective
basis for the difficulty calibration.

Judge-line positions come from :mod:`phira_pp.lineevents` (RPE).  Charts without
line-event support (PEC, for now) fall back to line-local note positions.
"""

from __future__ import annotations

import math

import numpy as np

from .models import Chart, NoteType

# Bump when feature definitions change, to invalidate the on-disk cache.
FEATURES_VERSION = 10

# RPE ``rotateEvents`` are DEGREES, not radians (measured on real packages:
# #10608 contains 0 / 3 / -3 / 270).  The raw value was previously stored as if
# it were a rate in rad/s (giving a meaningless p50 of 17.8 "rad/s") and — more
# importantly — the note offset was never rotated into world space at all, so
# every horizontal/travel feature on a rotated judging line was wrong.
# ``ROT_Y_SIGN`` fixes the sign of the vertical component; the Y axis convention
# is not documented for this loader, so both signs were scored by CV in
# scripts/exp_rotation.py and the better one is kept here.
ROT_Y_SIGN = -1.0

# Phira holds carry NO tail judgement, so a hold weighs like a tap that merely
# occupies a finger — and a very short hold (tap-and-lift) sits just below a tap.
# The ORDER `long_hold > tap > short_hold > flick > drag` is expert judgement
# from the project owner.  The magnitudes are the best set from the CV grid
# search in scripts/fit_type_weights.py (1.00 / 0.95 / 0.60 / 0.50 gives
# CV R2 0.838 vs 0.840 for raw key counting, i.e. essentially free), with
# long_hold raised to 1.05 to honour the stated strict ordering.
SHORT_HOLD_SEC = 0.15          # ~p40 of the measured hold-duration distribution
TYPE_WEIGHTS = {"tap": 1.00, "long": 1.05, "short": 0.95, "flick": 0.60, "drag": 0.50}

# Model inputs.  The judge-line features below (``line_speed_p90``,
# ``line_rot_p90``, ``hidden_frac``) ARE computed and cached, but are deliberately
# NOT listed here: a 5-fold cross-validation on 119 charts showed they reduce
# generalisation (CV R2 0.372 with vs 0.428 without), so they are excluded from
# the model until a formulation that actually helps is found.
FEATURE_NAMES = [
    "log_eff",
    "log_duration",
    "nps_peak",
    "aim_p95",
    "aim_mean",
    "chord_mean",
    "chord_max",
    "multi_frac",
    "hold_frac",
    "hold_density",
    "flick_frac",
    "drag_frac",
    "bpm_change",
    # Adopted after label cleaning (scripts/diag_dstar3.py): on the 655-chart
    # cleaned set, forward selection added these in order, CV R2 0.696 -> 0.756.
    # They encode "orderliness": evenly spaced onsets and steady movement
    # direction both pull difficulty DOWN, which pure density cannot express.
    "dt_cv",
    "dir_change_p80",
    "aim_p99",
    "seg_nps_p90",
    "hand_step_p95",
]

LINE_FEATURES = ["line_speed_p90", "line_rot_p90", "hidden_frac"]

# Extra signals that are computed and cached but not yet adopted.  A candidate
# is only moved into FEATURE_NAMES if forward selection (scripts/select_features.py)
# shows it improves cross-validated R2.
CANDIDATE_FEATURES = [
    "nps_peak_025",
    "nps_peak_500",
    "interval_p05",
    "chord_p90",
    "chord3_frac",
    "hold_concurrent_max",
    # remaining "orderliness" signals that did NOT clear the CV threshold
    "same_gap_frac",
    "onset_entropy",
    "aim_cv",
    "jack_frac",
    # per-type 物量 decomposition (see extract_features)
    "log_onsets",
    "log_taps",
    "log_holds",
    "log_flicks",
    "log_drags",
    "log_notes",
    "short_hold_frac",
    # segment aggregation: sustained level + hardest section (see PPSR audit)
    "seg_nps_p50",
    "seg_nps_p90",
    "seg_nps_max",
    "seg_speed_p95_mean",
    "seg_speed_p95_max",
    # 4-finger reachability (see PPSR audit item 3)
    "hand_step_p95",
    "hand_speed_p95",
    "hand_overreach_frac",
]

_CHORD_EPS = 0.035
_AIM_MAX_DT = 0.5
_DENSITY_WINDOW = 1.0
# Segment aggregation (see PPSR reference in .trae/rules/project_rules.md): the
# hardest section, not the chart-wide average, is what separates a 9-minute
# endurance chart from a 51-second burst.  10 s windows stepped by 5 s, plus one
# window aligned to the chart end so trailing content is not diluted.
_SEG_SIZE = 10.0
_SEG_STEP = 5.0


def _peak_window(times: np.ndarray, window: float) -> float:
    if times.size == 0:
        return 0.0
    best = 0
    j = 0
    for i in range(times.size):
        while times[i] - times[j] > window:
            j += 1
        best = max(best, i - j + 1)
    return best / window


def _chord_sizes(times: np.ndarray, eps: float) -> np.ndarray:
    if times.size == 0:
        return np.zeros(0)
    sizes = []
    start = 0
    for i in range(1, times.size + 1):
        if i == times.size or times[i] - times[start] > eps:
            sizes.append(i - start)
            start = i
    return np.asarray(sizes)


def _onset_times(times: np.ndarray, eps: float) -> np.ndarray:
    """First time of each chord cluster — gaps are then between *onsets*."""
    if times.size == 0:
        return times
    out = [float(times[0])]
    for value in times[1:]:
        if value - out[-1] > eps:
            out.append(float(value))
    return np.asarray(out)


def _p_speed(dx: np.ndarray, dy: np.ndarray, dt: np.ndarray, valid: np.ndarray, p: float):
    if not valid.any():
        return 0.0, 0.0
    spd = np.hypot(dx[valid], dy[valid]) / dt[valid]
    return float(np.percentile(spd, p)), float(spd.mean())


def _max_concurrent(intervals: list[tuple[float, float]]) -> float:
    """Maximum number of simultaneously open intervals."""
    events = []
    for start, end in intervals:
        events.append((start, 1))
        events.append((end, -1))
    events.sort()
    cur = best = 0
    for _, delta in events:
        cur += delta
        best = max(best, cur)
    return float(best)


FINGER_REST = np.array([-0.75, -0.25, 0.25, 0.75])
# Reference value from the PPSR scheme (calibrated there as the p95 of the max
# single-finger speed of the *simplest, human-cleared* tier).  Our x is normalised
# the same way (half-width = 1, world width 2), so the number transfers directly;
# scripts/exp_hand.py re-measures it on our own corpus.
FINGER_MAX_SPEED = 13.05


def _hand_stats(t: np.ndarray, wx: np.ndarray) -> tuple[float, float, float]:
    """4-finger nearest-neighbour assignment (PPSR G5/G9 style).

    The four fingers rest at :data:`FINGER_REST`; each note is taken by the finger
    already nearest to it, which then travels there.  Per-step travel and speed
    are collected across fingers.  Returns ``(step_p95, speed_p95, overreach_frac)``
    where speed is in half-widths/second and ``overreach_frac`` is the share of
    steps faster than :data:`FINGER_MAX_SPEED` — our proxy for "physically
    unreasonable for a single finger", which nothing else in the feature set can
    express.
    """
    pos = FINGER_REST.copy()
    last = np.full(4, np.nan)
    travels: list[float] = []
    speeds: list[float] = []
    for ti, xi in zip(t, wx):
        j = int(np.argmin(np.abs(pos - xi)))
        if np.isfinite(last[j]):
            d = abs(xi - pos[j])
            dt = ti - last[j]
            travels.append(d)
            if 0.0 < dt <= _AIM_MAX_DT:
                speeds.append(d / dt)
        pos[j] = xi
        last[j] = ti
    if not travels:
        return 0.0, 0.0, 0.0
    tr = np.asarray(travels)
    sp = np.asarray(speeds) if speeds else np.zeros(1)
    return (
        float(np.percentile(tr, 95)),
        float(np.percentile(sp, 95)),
        float((sp > FINGER_MAX_SPEED).mean()),
    )


def _segment_stats(
    t: np.ndarray,
    w_note: np.ndarray,
    sp_t: np.ndarray,
    sp_v: np.ndarray,
) -> tuple[float, float, float, float, float]:
    """Aggregate 10 s windows (5 s step, plus one aligned to the end).

    Returns ``(nps_p50, nps_p90, nps_max, speed_p95_mean, speed_p95_max)`` where
    the NPS is in *press-weighted* notes per second.  The p50 window is the
    sustained level, the max is the hardest section — together they say whether
    a chart is hard everywhere or only in one burst.
    """
    t0, t1 = float(t[0]), float(t[-1])
    span = t1 - t0
    if span <= _SEG_SIZE:
        starts = [t0]
    else:
        starts = list(np.arange(t0, t1 - _SEG_SIZE + 1e-9, _SEG_STEP))
        if abs(starts[-1] - (t1 - _SEG_SIZE)) > 1e-9:
            starts.append(t1 - _SEG_SIZE)
    nps, spd = [], []
    for s in starts:
        end = min(s + _SEG_SIZE, t1)
        width = end - s
        if width <= 1e-9:
            continue
        m = (t >= s) & (t < end)
        nps.append(float(w_note[m].sum()) / width)
        if sp_t.size:
            ms = (sp_t >= s) & (sp_t < end)
            if ms.any():
                spd.append(float(np.percentile(sp_v[ms], 95)))
    nps_a = np.asarray(nps)
    if not nps_a.size:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    spd_a = np.asarray(spd) if spd else np.zeros(1)
    return (
        float(np.percentile(nps_a, 50)),
        float(np.percentile(nps_a, 90)),
        float(nps_a.max()),
        float(spd_a.mean()),
        float(spd_a.max()),
    )


def _world_positions(chart: Chart, notes) -> tuple[np.ndarray, ...]:
    """Per-note on-screen x/y, line x/y, alpha, rotation and on-screen mask.

    Positions are in half-playfield-width units.  ``onscreen`` marks notes whose
    judging line is inside the playfield; charters sometimes teleport lines
    far off-screen with sentinel values, which must not count as finger travel.
    """
    scale = 1.0 / chart.half_width
    lines = chart.lines
    if lines is None:
        wx = np.asarray([n.x for n in notes])
        z = np.zeros_like(wx)
        return wx, z, z, z, np.ones_like(wx, dtype=bool), z, z
    wxs, wys, lxs, lys, als, rots = [], [], [], [], [], []
    for n in notes:
        px, py = lines.pos(n.line, n.beat)
        rot = math.radians(lines.rotate(n.line, n.beat))
        lxs.append(px)
        lys.append(py)
        # The note's local x offset must be rotated into world space by the
        # judging line's rotation at that instant — otherwise the measured
        # finger travel on a rotated line is simply wrong.
        off = n.x * chart.half_width
        wxs.append(px + off * math.cos(rot))
        wys.append(py + ROT_Y_SIGN * off * math.sin(rot))
        als.append(lines.alpha(n.line, n.beat))
        rots.append(rot)
    lx = np.asarray(lxs)
    ly = np.asarray(lys)
    onscreen = (np.abs(lx) <= chart.half_width) & (np.abs(ly) <= chart.half_height)
    return (
        np.asarray(wxs) * scale,
        np.asarray(wys) * scale,
        lx * scale,
        ly * scale,
        onscreen,
        np.asarray(als),
        np.asarray(rots),
    )


def extract_features(chart: Chart) -> dict[str, float] | None:
    notes = sorted(chart.playable_notes, key=lambda n: n.time)
    if len(notes) < 2:
        return None

    t = np.asarray([n.time for n in notes])
    types = np.asarray([int(n.type) for n in notes])
    holds = np.asarray([n.hold for n in notes])

    span = float(t[-1] - t[0])
    if span <= 0:
        return None

    wx, wy, lx, ly, onscreen, alpha, rot = _world_positions(chart, notes)

    dt = np.diff(t)
    valid = (dt > 1e-3) & (dt <= _AIM_MAX_DT) & onscreen[:-1] & onscreen[1:]

    aim_p95, aim_mean = _p_speed(np.diff(wx), np.diff(wy), dt, valid, 95)
    line_speed_p90, _ = _p_speed(np.diff(lx), np.diff(ly), dt, valid, 90)
    if valid.any():
        rot_spd = np.abs(np.diff(rot))[valid] / dt[valid]
        line_rot_p90 = float(np.percentile(rot_spd, 90))
        all_speed = np.hypot(np.diff(wx), np.diff(wy))[valid] / dt[valid]
        sp_t = ((t[:-1] + t[1:]) / 2.0)[valid]
        aim_p99 = float(np.percentile(all_speed, 99))
    else:
        line_rot_p90 = 0.0
        aim_p99 = 0.0
        all_speed = np.zeros(0)
        sp_t = np.zeros(0)
    hidden_frac = float((alpha < 0.5).mean())

    chords = _chord_sizes(t, _CHORD_EPS)
    multi_frac = float((chords >= 2).mean()) if chords.size else 0.0

    counts = {k: int((types == k).sum()) for k in (1, 2, 3, 4)}
    n = len(notes)

    hold_ivs = [(nn.time, nn.end_time) for nn in notes if nn.hold > 0.0]

    # -- press-weighted 物量 (see TYPE_WEIGHTS) ---------------------------
    hd = np.asarray([nn.hold for nn in notes if nn.type == NoteType.HOLD])
    n_short = int((hd < SHORT_HOLD_SEC).sum()) if hd.size else 0
    n_long = int(hd.size) - n_short
    w_note = np.full(n, TYPE_WEIGHTS["tap"], dtype=float)
    hold_m = types == NoteType.HOLD
    w_note[hold_m] = np.where(holds[hold_m] < SHORT_HOLD_SEC,
                              TYPE_WEIGHTS["short"], TYPE_WEIGHTS["long"])
    w_note[types == NoteType.FLICK] = TYPE_WEIGHTS["flick"]
    w_note[types == NoteType.DRAG] = TYPE_WEIGHTS["drag"]
    eff_notes = float(w_note.sum())

    # -- orderliness: dense-but-neat should read as EASIER ----------------
    # Inter-onset gaps (chord-clustered) describe the *rhythm*, so they separate
    # "fast but evenly spaced" from "fast and erratic" at equal density.
    onsets = _onset_times(t, _CHORD_EPS)
    og = np.diff(onsets)
    og = og[(og > 0.02) & (og < 2.0)]
    dt_cv = float(og.std() / og.mean()) if og.size > 1 and og.mean() > 0 else 0.0
    same_gap_frac = (
        float(np.mean(np.abs(og[1:] - og[:-1]) <= 0.05 * og[:-1])) if og.size > 1 else 0.0
    )
    onset_entropy = 0.0
    if og.size > 2:
        hist, _ = np.histogram(np.log(og), bins=12)
        p = hist[hist > 0] / hist.sum()
        onset_entropy = float(-(p * np.log(p)).sum() / np.log(12))

    step = np.hypot(np.diff(wx), np.diff(wy))[valid] if valid.any() else np.zeros(0)
    aim_cv = float(step.std() / step.mean()) if step.size > 1 and step.mean() > 1e-9 else 0.0

    dir_change_p80 = 0.0
    vx, vy = np.diff(wx), np.diff(wy)
    both = valid[:-1] & valid[1:] if valid.size > 1 else np.zeros(0, dtype=bool)
    if both.sum() >= 2:
        a = np.stack([vx[:-1][both], vy[:-1][both]], axis=1)
        b = np.stack([vx[1:][both], vy[1:][both]], axis=1)
        na, nb = np.linalg.norm(a, axis=1), np.linalg.norm(b, axis=1)
        good = (na > 1e-9) & (nb > 1e-9)
        if good.sum() >= 2:
            cos = (a[good] * b[good]).sum(1) / (na[good] * nb[good])
            dir_change_p80 = float(np.percentile(np.arccos(np.clip(cos, -1.0, 1.0)), 80))

    jack_frac = 0.0
    if dt.size:
        near = (np.abs(vx) < 0.04) & (np.abs(vy) < 0.04)
        jack_frac = float(np.mean(near & (dt < 0.12)))

    seg = _segment_stats(t, w_note, sp_t, all_speed)
    hand = _hand_stats(t, wx)

    return {
        "log_eff": float(np.log10(max(1.0, eff_notes))),
        "log_duration": float(np.log10(max(span, 1.0))),
        "nps_peak": _peak_window(t, _DENSITY_WINDOW),
        "aim_p95": aim_p95,
        "aim_mean": aim_mean,
        "line_speed_p90": line_speed_p90,
        "line_rot_p90": line_rot_p90,
        "hidden_frac": hidden_frac,
        "chord_mean": float(chords.mean()) if chords.size else 0.0,
        "chord_max": float(chords.max()) if chords.size else 0.0,
        "multi_frac": multi_frac,
        "hold_frac": counts[NoteType.HOLD] / n,
        "hold_density": float(holds.sum()) / span,
        "flick_frac": counts[NoteType.FLICK] / n,
        "drag_frac": counts[NoteType.DRAG] / n,
        "bpm_change": float(max(0, len(chart.bpm_points) - 1)),
        # candidates (not yet adopted)
        "nps_peak_025": _peak_window(t, 0.25),
        "nps_peak_500": _peak_window(t, 0.5),
        "interval_p05": float(np.percentile(dt, 5)) if dt.size else 0.0,
        "chord_p90": float(np.percentile(chords, 90)) if chords.size else 0.0,
        "chord3_frac": float((chords >= 3).mean()) if chords.size else 0.0,
        "aim_p99": aim_p99,
        "hold_concurrent_max": _max_concurrent(hold_ivs),
        "dt_cv": dt_cv,
        "same_gap_frac": same_gap_frac,
        "onset_entropy": onset_entropy,
        "aim_cv": aim_cv,
        "dir_change_p80": dir_change_p80,
        "jack_frac": jack_frac,
        # segment aggregation (candidates): sustained level + hardest section
        "seg_nps_p50": seg[0],
        "seg_nps_p90": seg[1],
        "seg_nps_max": seg[2],
        "seg_speed_p95_mean": seg[3],
        "seg_speed_p95_max": seg[4],
        # 4-finger reachability (candidates): see _hand_stats
        "hand_step_p95": hand[0],
        "hand_speed_p95": hand[1],
        "hand_overreach_frac": hand[2],
        # "count the presses, not the keys": a 4-key chord is one press, and a
        # drag is not a tap.  These decompose 物量 by onset and by note type so
        # the fit can learn each type's effective weight (no hand-picked weights).
        "log_onsets": float(np.log10(max(1, int(onsets.size)))),
        "log_taps": float(np.log10(1 + counts[NoteType.TAP])),
        "log_holds": float(np.log10(1 + counts[NoteType.HOLD])),
        "log_flicks": float(np.log10(1 + counts[NoteType.FLICK])),
        "log_drags": float(np.log10(1 + counts[NoteType.DRAG])),
        # raw key count and the short-hold share, kept for diagnostics
        "log_notes": float(np.log10(n)),
        "short_hold_frac": (float(n_short) / n) if n else 0.0,
    }


def feature_vector(features: dict[str, float]) -> np.ndarray:
    return np.asarray([features[name] for name in FEATURE_NAMES], dtype=float)
