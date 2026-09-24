"""Command-line entry point: compute 定数/D* and PP from the live Phira API.

    python scripts/pp.py chart 26795
    python scripts/pp.py record 123456789
    python scripts/pp.py user 5104
"""

import argparse
import dataclasses

from phira_pp.pipeline import OSU_DECAY, PPEngine, osu_total_pp


def _chart_header(res):
    m = res.meta
    notes = f" notes={res.note_count}" if res.note_count else ""
    d = f"{res.d_star:.2f}" if res.d_star is not None else "n/a"
    used = f"{res.difficulty:.2f}" if res.difficulty is not None else "n/a"
    print(f"#{m.id} {m.name} | {m.level} | 定数={m.difficulty:.2f} D*={d} -> "
          f"采用={used} [{res.difficulty_source}] | "
          f"ranked={m.ranked} rating={m.rating:.2f}({m.rating_count}){notes}")


def cmd_chart(engine, chart_id, top):
    res = engine.chart(chart_id)
    _chart_header(res)
    if res.difficulty is None:
        why = res.difficulty_source
        if res.d_star is None:
            why += "; chart unparsable or unsupported format"
        print(f"no usable difficulty [{why}]")
        return
    print(f"{'score':>8} {'acc':>8} {'无暇度':>9} {'combo':>6} {'pp':>8}")
    for p in engine.chart_top_plays(chart_id, limit=top):
        r = p.record
        print(f"{r.score:>8d} {r.accuracy * 100:>7.2f}% {r.std * 1000:>7.2f}ms "
              f"{r.max_combo:>6d} {p.pp:>8.1f}")


def cmd_record(engine, record_id):
    rec = engine.client.get_record(record_id)
    p = engine.play(rec)
    _chart_header(engine.chart(rec.chart))
    print(f"player={rec.player} score={rec.score} acc={rec.accuracy*100:.2f}% "
          f"P/G/B/M={rec.perfect}/{rec.good}/{rec.bad}/{rec.miss} "
          f"combo={rec.max_combo}/{rec.total_judged} 无暇度={rec.std*1000:.2f}ms")
    if p.breakdown is None:
        print("no PP (chart D* unavailable)")
        return
    b = p.breakdown
    print(f"  难度={b.difficulty:.2f} acc_factor={b.acc_factor:.4f} "
          f"precision={b.precision_factor:.4f} error={b.error_factor:.4f}")
    print(f"  PP = {b.pp:.1f}")


def cmd_user(engine, user_id, top):
    results = engine.player_best_plays(user_id, limit=top)
    if not results:
        print("no records")
        return
    print(f"player {user_id}: {len(results)} charts (by PP)")
    print(f"{'pp':>8}  {'采用':>6} {'定数':>6}  chart")
    for p in results:
        d = f"{p.difficulty:.2f}" if p.difficulty is not None else "  n/a"
        print(f"{p.pp:>8.1f}  {d:>6} {p.chart.difficulty:>6.2f}  #{p.chart.id} {p.chart.name}")


def cmd_play(engine, user_id, chart_id, max_scan):
    user = engine.client.get_user(user_id)
    print(f"player {user.get('id')} {user.get('name')} (rks={user.get('rks'):.2f})")
    result, source = engine.player_chart_play(user_id, chart_id, max_scan=max_scan)
    if result is None:
        if source == "error":
            print(f"查询谱面 #{chart_id} 失败（上游接口/网络错误）。")
        else:
            print(f"该玩家在谱面 #{chart_id} 上没有成绩（未游玩或未上传）。")
        return
    _chart_header(engine.chart(chart_id))
    r = result.record
    print(f"score={r.score} acc={r.accuracy*100:.2f}% "
          f"P/G/B/M={r.perfect}/{r.good}/{r.bad}/{r.miss} "
          f"combo={r.max_combo}/{r.total_judged} 无暇度={r.std*1000:.2f}ms")
    print(f"来源: {source}")
    if result.breakdown is None:
        print("no PP (chart D* unavailable)")
        return
    b = result.breakdown
    print(f"  难度={b.difficulty:.2f} acc_factor={b.acc_factor:.4f} "
          f"precision={b.precision_factor:.4f} error={b.error_factor:.4f}")
    print(f"  PP = {b.pp:.1f}")


def cmd_best(engine, user_id, n, per_chart, workers, full=False):
    user = engine.client.get_user(user_id)
    print(f"player {user.get('id')} {user.get('name')} (rks={user.get('rks'):.2f})")
    if full:
        print("全量模式：ranked + regular 全部谱面（非定数谱用 D*，首次需下载谱面包，较慢）…")
        last = [0]

        def prog(done, total, phase):
            if done == total or done - last[0] >= 25:
                last[0] = done
                print(f"\r  {phase}: {done}/{total}", end="", flush=True)

        results, stats = engine.best_plays_full(user_id, workers=workers, progress=prog)
        print()
    else:
        print(f"scanning {len(engine.anchors)} charts from the 定数表 set ...")
        results, stats = engine.scan_best_plays(user_id, per_chart=per_chart, workers=workers)
    print(f"stats: {stats}")
    top = results[:n]
    if not top:
        print("no records found in this chart set")
        return
    total = osu_total_pp([p.pp for p in top])
    print(f"\n总 PP = {total:.1f}   (osu 加权 0.95^i，取前 {len(top)} 项)")
    print(f"{'#':>4} {'pp':>8} {'加权':>8} {'定数':>6} {'采用':>6}  chart")
    for i, p in enumerate(top, start=1):
        w = OSU_DECAY ** (i - 1)
        print(f"{i:>4} {p.pp:>8.1f} {p.pp*w:>8.1f} {p.chart.difficulty:>6.2f} "
              f"{(p.difficulty or 0):>6.2f}  #{p.chart.id} {p.chart.name[:40]}")


def main():
    parser = argparse.ArgumentParser(prog="pp", description="Phira D* / PP calculator")
    sub = parser.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("chart", help="D* and top-play PP for a chart")
    c.add_argument("chart_id", type=int)
    c.add_argument("-n", "--top", type=int, default=10)

    r = sub.add_parser("record", help="PP breakdown for one record")
    r.add_argument("record_id", type=int)

    u = sub.add_parser("user", help="per-chart PP for a player's best pool")
    u.add_argument("user_id", type=int)
    u.add_argument("-n", "--top", type=int, default=20)

    pl = sub.add_parser("play", help="a player's record on a specific chart")
    pl.add_argument("user_id", type=int)
    pl.add_argument("chart_id", type=int)
    pl.add_argument("--max-scan", type=int, default=600,
                    help="how many chart records to scan for the player")

    b = sub.add_parser("best", help="scan the 定数表 set and build a best-N list")
    b.add_argument("user_id", type=int)
    b.add_argument("-n", "--top", type=int, default=100)
    b.add_argument("--per-chart", type=int, default=30,
                   help="(legacy) records per chart inspected; unused by the direct route")
    b.add_argument("--workers", type=int, default=32)
    b.add_argument("--all", action="store_true",
                   help="全量：扫描 ranked + regular 全部谱面（非定数谱用 D* 兜底，慢）")

    for p in (c, r, u, pl, b):
        p.add_argument("--exp", type=float, default=None,
                       help="difficulty exponent override (policy parameter, default 2.0)")

    args = parser.parse_args()
    engine = PPEngine()
    if args.exp:
        engine.params = dataclasses.replace(engine.params, diff_exp=args.exp)
    if args.cmd == "chart":
        cmd_chart(engine, args.chart_id, args.top)
    elif args.cmd == "record":
        cmd_record(engine, args.record_id)
    elif args.cmd == "user":
        cmd_user(engine, args.user_id, args.top)
    elif args.cmd == "best":
        cmd_best(engine, args.user_id, args.top, args.per_chart, args.workers, args.all)
    else:
        cmd_play(engine, args.user_id, args.chart_id, args.max_scan)


if __name__ == "__main__":
    main()
