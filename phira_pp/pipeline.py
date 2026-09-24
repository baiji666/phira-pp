"""End-to-end engine: chart difficulty (D*) and per-play PP.

Ties together the pieces built so far:

    chart package -> features -> D* (fitted model) -> PP (record + D*)

All heavy work (package download, parsing, features) is cached on disk by
:class:`~phira_pp.dataset.Dataset`.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from .api import PhiraClient, _meta_from_dict, _record_from_dict, load_token
from .dataset import Dataset, load_model
from .models import ChartMeta, PlayRecord
from .pp import PPBreakdown, PPParams, performance_pp

ANCHOR_FILE = "anchors.json"
KV_FILE = "kv_diff.json"
SUBJECTIVE_FILE = "subjective_diff.json"
OVERRIDE_FILE = "difficulty_override.json"
SUBJECTIVE_SOURCE = "定数表 (主观)"
SUONASI_SOURCE = "定数表 (Suonasi)"
# Explicit expert values, highest priority.  D* is a fit to the 定数 labels, so it
# can never exceed them for a chart whose label is lower — deviating on purpose is
# therefore a POLICY decision and must be declared, not smuggled into the model.
# This mirrors the reference implementation's manual override layer.
OVERRIDE_SOURCE = "专家覆盖 (override)"
# The subjective 定数表 deliberately never rates 18.60+, so its value is a FLOOR
# for the (unbounded) D* model rather than a ceiling.  Measured: this raises 6
# charts and lowers none (#39209 18.59 -> 19.84, #30942 18.56 -> 19.34, ...).
SUBJECTIVE_FLOOR_SOURCE = "D* (高于主观表)"

# osu!'s total-pp weighting: the best play counts fully, then 0.95^rank.
OSU_DECAY = 0.95

# D* is a ridge fit on chart features: well outside its training labels it
# extrapolates without bound (raw -91.15 and +21.5 were observed on real charts)
# and difficulty**diff_exp then explodes (15.5M pp).  Such predictions are NOT
# trustworthy, so they are excluded and counted rather than clamped onto the
# boundary — clamping a garbage 21.4 to 20.0 would park it next to a real 20.0
# and push it to the top of the list.
DSTAR_MIN = 0.0
DSTAR_MAX = 20.0
# Boundary tolerance: a prediction sitting on the label ceiling (e.g. #22206 at
# 20.0015) is numerical noise, not the unbounded extrapolation this guard exists
# to catch (raw -91.15 / +21.5 / +41.3 were observed).  0.05 is 7% of the model's
# own RMSE (0.686) and admits exactly one chart in the corpus (#22206).
DSTAR_TOL = 0.05


def _dstar_usable(value: float | None) -> bool:
    """True when a D* prediction may be used (inside the label range + tolerance)."""
    return value is not None and (DSTAR_MIN - DSTAR_TOL) <= value <= (DSTAR_MAX + DSTAR_TOL)


def osu_total_pp(pps: list[float], decay: float = OSU_DECAY) -> float:
    """Weighted total exactly as osu! does: sum(pp_i * 0.95^i)."""
    return float(sum(p * (decay ** i) for i, p in enumerate(pps)))


def _pick_best_row(rows: list[dict]) -> dict | None:
    """Fallback pick among a chart's rows when no 定数 is known.

    Rows from ``/record?player=&chart=`` carry a server-set ``best`` flag; use it
    when present, otherwise fall back to the highest score.  Verified: the flagged
    row's score always equals ``/record/best/{chart}``.

    NOTE: when a 定数 *is* known, :func:`_best_play_row` is used instead — see
    there for why score is the wrong key.
    """
    if not rows:
        return None
    flagged = [r for r in rows if r.get("best")]
    pool = flagged or rows
    return max(pool, key=lambda r: float(r.get("score") or 0))


def _best_play_row(rows: list[dict], difficulty: float | None,
                   params: PPParams) -> dict | None:
    """The row that yields the highest PP for this chart.

    The endpoint returns up to 20 records per chart, and the highest score is
    NOT the highest PP: PP is driven by accuracy/无暇度/漏键, so a slightly lower
    score with cleaner hits scores more.  SuonasiOS reads the whole history and
    selects by a rule (its default is ``highestAccuracy``); PP-max dominates both
    that and score-max.

    Verified on real data (459003, 442-chart community set): score-max gives a
    Best-100 of 20085.1, accuracy-max 20363.4, PP-max 20371.9 (+286.8 vs the old
    score-based pick, and +8.5 over accuracy-max).  93/357 charts differ.

    Falls back to :func:`_pick_best_row` when the difficulty is unknown, so the
    behaviour is never worse than before.
    """
    if not rows:
        return None
    if difficulty is None:
        return _pick_best_row(rows)
    best_row, best_pp = None, None
    for row in rows:
        pp = performance_pp(difficulty, _record_from_dict(row), params).pp
        if best_pp is None or pp > best_pp:
            best_row, best_pp = row, pp
    return best_row


def load_tables(cache_dir: str | Path) -> dict[int, tuple[float, str]]:
    """``{chart_id: (difficulty, source_label)}`` — the community 定数 tables.

    Priority (highest first), mirroring the difficulty chain:

    1. ``kv_diff.json`` — the machine-readable table the SuonasiOS app itself
       fetches from its KV service (``https://suonasi.07210700.xyz/kv/diff``,
       found in libapp.so).  It lists exact chart ids, so nothing is inferred.
    2. ``subjective_diff.json`` — the human 体感定数 table built from
       ``data/subjective_diff.xlsx`` (see ``scripts/build_subjective_diff.py``).
       It only fills the ids the Suonasi table does **not** already cover: on
       overlap the Suonasi value wins (explicit requester rule).
    3. ``anchors.json`` — the old OCR + title-verified set.  Used only when
       neither machine-readable table is present.

    A broken/unparsable table is skipped, never fatal.
    """
    tables: dict[int, tuple[float, str]] = {}

    kv = Path(cache_dir) / KV_FILE
    if kv.exists():
        try:
            data = json.loads(kv.read_text("utf-8"))
            rows = data.get("rows", data if isinstance(data, list) else [])
            for r in rows:
                tables[int(r["id"])] = (float(r["difficulty"]), SUONASI_SOURCE)
        except Exception:  # noqa: BLE001 - fall through to the next table
            pass

    subjective = Path(cache_dir) / SUBJECTIVE_FILE
    if subjective.exists():
        try:
            data = json.loads(subjective.read_text("utf-8"))
            for r in data.get("rows", []):
                cid = int(r["id"])
                if cid not in tables:  # Suonasi wins on overlap
                    tables[cid] = (float(r["difficulty"]), SUBJECTIVE_SOURCE)
        except Exception:  # noqa: BLE001 - never fatal
            pass

    # expert overrides win over the whole 定数 chain (a ranked label still wins,
    # being the charter's own authoritative value).  They are the one place where
    # a value may deliberately disagree with the fitted model.
    override = Path(cache_dir) / OVERRIDE_FILE
    if override.exists():
        try:
            for r in json.loads(override.read_text("utf-8")).get("rows", []):
                tables[int(r["id"])] = (float(r["value"]), OVERRIDE_SOURCE)
        except Exception:  # noqa: BLE001 - never fatal
            pass

    if tables:
        return tables

    path = Path(cache_dir) / ANCHOR_FILE
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text("utf-8"))
    except Exception:  # noqa: BLE001 - a broken table must not crash the app
        return {}
    return {int(r["id"]): (float(r["group"]), "定数表 (OCR)")
            for r in data.get("resolved", [])}


@dataclass
class ChartResult:
    meta: ChartMeta
    d_star: float | None
    note_count: int | None
    # Effective difficulty used for PP and where it came from.  For ranked charts
    # the charter 定数 IS the label our model tries to predict, so using D* there
    # would inject the model's own ~0.6 error for no benefit; D* is the fallback
    # only where no vetted 定数 exists.
    difficulty: float | None = None
    difficulty_source: str = "-"


@dataclass
class PlayResult:
    record: PlayRecord
    chart: ChartMeta
    d_star: float | None
    breakdown: PPBreakdown | None
    difficulty: float | None = None
    difficulty_source: str = "-"

    @property
    def pp(self) -> float:
        return self.breakdown.pp if self.breakdown else 0.0


class PPEngine:
    def __init__(
        self,
        cache_dir: str | Path = "data",
        client: PhiraClient | None = None,
        model_path: str | Path = "data/difficulty_model.json",
        params: PPParams | None = None,
        token: str | None = None,
    ):
        self.client = client or PhiraClient(token=token if token is not None else load_token())
        self.dataset = Dataset(cache_dir, client=self.client)
        self.model = load_model(model_path)
        self.params = params or PPParams()
        self.tables = load_tables(cache_dir)
        # {chart_id: difficulty} view of the community tables, kept for the
        # "scan the whole 定数表 set" default chart list.
        self.anchors = {cid: d for cid, (d, _src) in self.tables.items()}
        self._chart_cache: dict[int, ChartResult] = {}

    # -- difficulty -----------------------------------------------------
    def chart(self, chart_id: int) -> ChartResult:
        if chart_id in self._chart_cache:
            return self._chart_cache[chart_id]
        meta = self.client.get_chart(chart_id)
        feats = self.dataset.get_features(meta)
        d_star = self.model.predict_features(feats) if feats else None
        if meta.ranked and meta.difficulty > 0:
            difficulty, source = float(meta.difficulty), "定数 (ranked)"
        elif chart_id in self.tables:
            difficulty, source = self._table_with_floor(chart_id, d_star)
        elif _dstar_usable(d_star):
            difficulty, source = float(d_star), "D* (模型)"
        elif d_star is not None:
            # Outside the training label range the ridge extrapolates without
            # bound; such a value is excluded (never clamped), exactly as in
            # best_plays_full.  Raising this to the caller instead of returning a
            # garbage 41.3 keeps a single query from showing a 1e5 pp play.
            difficulty, source = None, "D* 越界(已排除)"
        else:
            difficulty, source = None, "-"
        result = ChartResult(
            meta=meta,
            d_star=d_star,
            note_count=int(feats["_note_count"]) if feats and "_note_count" in feats else None,
            difficulty=difficulty,
            difficulty_source=source,
        )
        self._chart_cache[chart_id] = result
        return result

    # -- single play ----------------------------------------------------
    def play(self, record: PlayRecord) -> PlayResult:
        res = self.chart(record.chart)
        breakdown = (
            performance_pp(res.difficulty, record, self.params) if res.difficulty else None
        )
        return PlayResult(
            record=record, chart=res.meta, d_star=res.d_star, breakdown=breakdown,
            difficulty=res.difficulty, difficulty_source=res.difficulty_source,
        )

    # -- convenience views ---------------------------------------------
    def chart_top_plays(self, chart_id: int, limit: int = 15) -> list[PlayResult]:
        res = self.chart(chart_id)
        recs = list(self.client.iter_chart_records(chart_id, max_records=limit))
        recs.sort(key=lambda r: -r.score)
        out = []
        for r in recs:
            breakdown = (
                performance_pp(res.difficulty, r, self.params) if res.difficulty else None
            )
            out.append(PlayResult(record=r, chart=res.meta, d_star=res.d_star,
                                  breakdown=breakdown, difficulty=res.difficulty,
                                  difficulty_source=res.difficulty_source))
        return out

    def player_best_plays(self, user_id: int, limit: int = 20) -> list[PlayResult]:
        """Compute PP for every chart in a player's best-pool (best-first)."""
        pool = self.client.get_best_pool(user_id)
        rows = pool.get("bestPool", pool if isinstance(pool, list) else [])
        ids = [row.get("record") or row.get("id") for row in rows]
        ids = [i for i in ids if i is not None]
        detail = {r.id: r for r in self.client.get_records(ids)} if ids else {}
        results = [self.play(detail[i]) for i in ids if i in detail]
        results.sort(key=lambda p: -p.pp)
        return results[:limit]

    # -- bulk scan over the 定数表 chart set -----------------------------
    def _table_with_floor(self, chart_id: int, d_star: float | None
                          ) -> tuple[float, str]:
        """Community-table value, with the 主观表 acting as a FLOOR for D*.

        The table's own rule is "不会对 18.60 及以上进行定数", so it cannot express
        the top of the range; when D* (a continuous fit over [0, 20]) is higher it
        wins.  Measured: raises 6 charts, lowers none (#39209 18.59→19.84,
        #30942 18.56→19.34, #22206 →20.00).  Suonasi values are used as-is.
        """
        value, source = self.tables[chart_id]
        if (source == SUBJECTIVE_SOURCE and _dstar_usable(d_star) and d_star > value):
            return float(d_star), SUBJECTIVE_FLOOR_SOURCE
        return value, source

    def anchor_difficulty(self, chart_id: int, meta: ChartMeta) -> tuple[float | None, str]:
        """Difficulty used for PP, by priority: ranked 定数 -> community table -> none.

        The community table is the Suonasi KV table with the subjective 定数表
        filling the ids Suonasi does not cover (see :func:`load_tables`); the
        subjective value is a floor for D* (see :meth:`_table_with_floor`).
        """
        if meta.ranked and meta.difficulty > 0:
            return float(meta.difficulty), "定数 (ranked)"
        if chart_id in self.tables:
            value, source = self.tables[chart_id]
            if source == SUBJECTIVE_SOURCE:
                # only the subjective table needs D*, so KV charts stay download-free
                return self._table_with_floor(chart_id, self.d_star(meta))
            return value, source
        return None, "-"

    def best_plays_direct(
        self, user_id: int, chart_ids: list[int] | None = None,
        workers: int = 32,
    ) -> tuple[list[PlayResult], dict]:
        """Best record of ``user_id`` on every chart, one request per chart.

        Uses ``/record?player=&chart=`` — the real player x chart route (verified
        on real data: no token needed, works for any player, and the rows always
        include that account's best with ``std``/无暇度).  Coverage is therefore
        complete, with none of the rank-depth blind spots of a top-N page scan.
        """
        ids = list(chart_ids) if chart_ids else sorted(self.anchors)
        metas = {m.id: m for m in self.client.get_charts(ids)}

        def one(cid: int):
            try:
                return cid, self.client.query_player_chart(user_id, cid), True
            except Exception:  # noqa: BLE001 - counted, never hidden
                return cid, None, False

        played: dict[int, list[dict]] = {}
        scanned = failed = 0
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for cid, rows, ok in ex.map(one, ids):
                scanned += 1
                if not ok:
                    failed += 1
                elif rows:
                    played[cid] = rows

        results: list[PlayResult] = []
        for cid, rows in played.items():
            meta = metas.get(cid)
            if meta is None:
                continue
            diff, source = self.anchor_difficulty(cid, meta)
            row = _best_play_row(rows, diff, self.params)
            if row is None:
                continue
            rec = _record_from_dict(row)
            breakdown = performance_pp(diff, rec, self.params) if diff else None
            results.append(PlayResult(record=rec, chart=meta, d_star=None,
                                      breakdown=breakdown, difficulty=diff,
                                      difficulty_source=source))
        results.sort(key=lambda p: -p.pp)
        stats = {
            "mode": "direct(/record?player=&chart=)",
            "charts_in_set": len(ids),
            "scanned": scanned,
            "scan_failed": failed,
            "played_charts": len(played),
            "found": len(results),
            "workers": workers,
        }
        return results, stats

    def scan_best_plays(
        self, user_id: int, chart_ids: list[int] | None = None,
        per_chart: int = 30, workers: int = 32, use_pool: bool = True,
        detail_top: int | None = 150,
    ) -> tuple[list[PlayResult], dict]:
        """Best record of ``user_id`` on each chart of the 定数表 set.

        ``per_chart`` / ``use_pool`` / ``detail_top`` are kept only so existing
        callers keep working; the direct player x chart route
        (:meth:`best_plays_direct`) makes them unnecessary.
        """
        return self.best_plays_direct(user_id, chart_ids, workers=workers)

    def player_chart_play(
        self, user_id: int, chart_id: int, max_scan: int = 600
    ) -> tuple[PlayResult | None, str]:
        """A player's best record on one chart via ``/record?player=&chart=``.

        Verified: that route needs no token, works for any player, and returns the
        account's records on the chart (up to 20, including its ``best: true`` row)
        with ``std``/无暇度 — so the answer is exact in a single request.  The row
        chosen is the one with the **highest PP** among them, not the highest
        score (see :func:`_best_play_row`).  ``max_scan`` is retained only for
        signature compatibility.  Returns ``(result, source)`` where source is
        ``direct`` / ``not_found`` / ``error``.
        """
        try:
            rows = self.client.query_player_chart(user_id, chart_id)
        except Exception:  # noqa: BLE001 - surfaced as a source, never hidden
            return None, "error"
        row = _best_play_row(rows, self.chart(chart_id).difficulty, self.params)
        if row is None:
            return None, "not_found"
        return self.play(_record_from_dict(row)), "direct"

    # -- full catalogue (all ranked + regular charts) --------------------
    def catalogue(self, progress=None, workers: int = 16
                  ) -> tuple[dict[int, ChartMeta], int]:
        """Every chart of the ``regular`` division, keyed by id (+ failed pages).

        ``division="regular"`` inherently leaves out the 整活(troll) / 纯配置
        (plain) / 观赏(visual) / special / SP divisions — exactly the required
        exclusion.  Ranked charts are a subset of regular (verified on the live
        catalogue: ``ranked=true`` -> 583, ``regular & ranked=true`` -> 583,
        and 0 ranked in any other division), so this single filter is enough.

        Pages are independent, so they are fetched concurrently (16 at a time);
        paging sequentially over 9644 rows / 30 per page took ~4 minutes.
        """
        first = self.client.search_charts(page=1, pageNum=30, order="rating",
                                          division="regular")
        rows0 = first.get("results") or []
        total = int(first.get("count") or 0) or len(rows0)
        pages = max(1, (total + 29) // 30)

        metas: dict[int, ChartMeta] = {}
        for row in rows0:
            meta = _meta_from_dict(row)
            metas[meta.id] = meta
        if progress:
            progress(len(metas), total, "枚举谱面目录")

        page_failed = 0

        def fetch(page: int):
            try:
                data = self.client.search_charts(page=page, pageNum=30,
                                                 order="rating", division="regular")
                return data.get("results") or []
            except Exception:  # noqa: BLE001 - counted, never hidden
                return None

        if pages > 1:
            done = 1
            with ThreadPoolExecutor(max_workers=workers) as ex:
                for rows in ex.map(fetch, range(2, pages + 1)):
                    done += 1
                    if rows is None:
                        page_failed += 1
                    else:
                        for row in rows:
                            meta = _meta_from_dict(row)
                            metas[meta.id] = meta
                    if progress and (done % 20 == 0 or done == pages):
                        progress(len(metas), total,
                                 f"枚举谱面目录（失败页 {page_failed}）")
        return metas, page_failed

    def d_star(self, meta: ChartMeta) -> float | None:
        """D* for a chart from its package features; ``None`` if unparsable.

        The package is downloaded on first use and cached in ``data/packages``.
        """
        feats = self.dataset.get_features(meta)
        if not feats:
            return None
        try:
            return float(self.model.predict_features(feats))
        except Exception:  # noqa: BLE001 - reported as "no difficulty"
            return None

    def best_plays_full(self, user_id: int, workers: int = 32, dstar_workers: int = 8,
                        progress=None) -> tuple[list[PlayResult], dict]:
        """Best100 over the **whole** ranked + regular catalogue.

        Difficulty priority is unchanged (ranked 定数 -> 定数表 -> D*).  The D*
        fallback must download and parse each played chart's package, which is
        why this mode is local-only and takes minutes on a first run.
        ``progress(done, total, phase)`` is called during each stage.
        """
        metas, page_failed = self.catalogue(progress)
        ids = sorted(metas)
        total = len(ids)

        def one(cid: int):
            try:
                return cid, self.client.query_player_chart(user_id, cid), True
            except Exception:  # noqa: BLE001 - counted, never hidden
                return cid, None, False

        played: dict[int, list[dict]] = {}
        scan_failed = 0
        done = 0
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for cid, rows, ok in ex.map(one, ids):
                done += 1
                if not ok:
                    scan_failed += 1
                elif rows:
                    played[cid] = rows
                if progress and (done % 50 == 0 or done == total):
                    progress(done, total, f"查询成绩（失败 {scan_failed}）")

        base: dict[int, tuple[float | None, str]] = {}
        need_dstar: list[int] = []
        for cid in played:
            diff, source = self.anchor_difficulty(cid, metas[cid])
            base[cid] = (diff, source)
            if diff is None:
                need_dstar.append(cid)

        dstar: dict[int, float] = {}
        dstar_failed = 0
        dstar_out_of_range = 0
        if need_dstar:
            def compute(cid: int):
                return cid, self.d_star(metas[cid])

            n = 0
            with ThreadPoolExecutor(max_workers=dstar_workers) as ex:
                for cid, value in ex.map(compute, need_dstar):
                    n += 1
                    if value is None:
                        dstar_failed += 1
                    elif not _dstar_usable(value):
                        dstar_out_of_range += 1   # excluded, counted, never trusted
                    else:
                        dstar[cid] = value
                    if progress and (n % 10 == 0 or n == len(need_dstar)):
                        progress(n, len(need_dstar),
                                 f"计算 D*（失败 {dstar_failed} / 越界 {dstar_out_of_range}）")

        results: list[PlayResult] = []
        no_difficulty = 0
        for cid, rows in played.items():
            diff, source = base[cid]
            if diff is None:
                if cid in dstar:
                    diff, source = dstar[cid], "D* (模型)"
                else:
                    no_difficulty += 1
                    continue
            row = _best_play_row(rows, diff, self.params)
            if row is None:
                continue
            meta = metas[cid]
            rec = _record_from_dict(row)
            results.append(PlayResult(
                record=rec, chart=meta, d_star=None,
                breakdown=performance_pp(diff, rec, self.params),
                difficulty=diff, difficulty_source=source,
            ))
        results.sort(key=lambda p: -p.pp)
        stats = {
            "mode": "full(ranked+regular)",
            "charts_in_set": total,
            "catalogue_page_failed": page_failed,
            "scanned": total,
            "scan_failed": scan_failed,
            "played_charts": len(played),
            "dstar_needed": len(need_dstar),
            "dstar_ok": len(dstar),
            "dstar_failed": dstar_failed,
            "dstar_out_of_range": dstar_out_of_range,
            "no_difficulty": no_difficulty,
            "found": len(results),
            "workers": workers,
        }
        return results, stats
