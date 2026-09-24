"""Remaining facts for "Best100 over all ranked+regular charts":
paging limits, whether ranked is a subset of regular, and scan throughput.
"""

import time
from concurrent.futures import ThreadPoolExecutor

from phira_pp.api import PhiraClient

c = PhiraClient()


def cnt(**kw):
    try:
        return c.search_charts(page=1, pageNum=1, **kw).get("count")
    except Exception as exc:  # noqa: BLE001
        return f"ERR {type(exc).__name__} {str(exc)[:40]}"


print("ranked='true'                     ->", cnt(ranked="true"))
print("regular & ranked='true'           ->", cnt(division="regular", ranked="true"))
print("plain & ranked='true'             ->", cnt(division="plain", ranked="true"))
print("troll & ranked='true'             ->", cnt(division="troll", ranked="true"))
print("visual & ranked='true'            ->", cnt(division="visual", ranked="true"))
print("regular (no ranked)               ->", cnt(division="regular"))

print("\npageNum limit on /chart:")
for pn in (30, 100, 500, 1000):
    try:
        d = c.search_charts(page=1, pageNum=pn, division="regular")
        print(f"  pageNum={pn:<5d} rows={len(d.get('results') or [])}")
    except Exception as exc:  # noqa: BLE001
        print(f"  pageNum={pn:<5d} ERR {type(exc).__name__} {str(exc)[:50]}")

# Throughput: how long would ~9600 per-chart record requests take?
from phira_pp.api import PhiraClient as PC
import requests

ids = list(range(1, 401))


def bench(workers, hosts):
    def one(i):
        url = f"https://{hosts[i % len(hosts)]}/record"
        try:
            requests.get(url, params={"player": 459003, "chart": i},
                         headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        except Exception:  # noqa: BLE001
            pass
    t = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(one, ids))
    dt = time.time() - t
    print(f"  workers={workers:<3d} hosts={len(hosts)}: {len(ids)} req in {dt:.1f}s "
          f"-> {len(ids) / dt:.0f} req/s  => 9644 req ≈ {9644 / (len(ids) / dt):.0f}s")


print("\nthroughput (400 chart-record requests):")
bench(32, ["api.phira.cn"])
bench(32, ["phira.5wyxi.com"])
bench(32, ["api.phira.cn", "phira.5wyxi.com"])
bench(48, ["api.phira.cn", "phira.5wyxi.com"])
