"""Corrected throughput test using keep-alive sessions (as the engine does)."""

import time
from concurrent.futures import ThreadPoolExecutor

from phira_pp.api import PhiraClient

A = PhiraClient(base="https://api.phira.cn")
B = PhiraClient(base="https://phira.5wyxi.com")
ids = list(range(1, 401))
U = 0


def bench(workers, clients, label):
    def one(i):
        cl = clients[i % len(clients)]
        try:
            cl.query_player_chart(U, i)
        except Exception:  # noqa: BLE001
            pass
    t = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(one, ids))
    dt = time.time() - t
    rate = len(ids) / dt
    print(f"  {label:<34s} {len(ids)} req in {dt:5.1f}s -> {rate:5.1f} req/s "
          f"=> 9644 req ≈ {9644 / rate:5.0f}s ({9644 / rate / 60:.1f} min)")


print("throughput (400 per-chart record requests, keep-alive):")
bench(32, [A], "32w, 1 host (api.phira.cn)")
bench(32, [B], "32w, 1 host (phira.5wyxi.com)")
bench(32, [A, B], "32w, 2 hosts round-robin")
bench(64, [A, B], "64w, 2 hosts round-robin")
bench(16, [A, B], "16w, 2 hosts round-robin")
