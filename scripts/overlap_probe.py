"""Feasibility probe: can a CONNECTED player-chart comparison graph be built?

Per-chart top-record queries give ~1.3 records per player, so player and chart
effects cannot be separated.  A player's own record pool (``/record/get-pool``)
lists the charts that player has played, which should create overlap by
construction.  This probes that overlap before committing to an IRT fit.
"""

import collections
import sys

from phira_pp.api import PhiraClient


def connected_components(edges):
    """Largest connected component size over the bipartite player-chart graph."""
    adj = collections.defaultdict(set)
    for p, c in edges:
        adj[("p", p)].add(("c", c))
        adj[("c", c)].add(("p", p))
    seen = set()
    best = 0
    for node in adj:
        if node in seen:
            continue
        stack = [node]
        size = 0
        seen.add(node)
        while stack:
            cur = stack.pop()
            size += 1
            for nxt in adj[cur]:
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        best = max(best, size)
    return best, len(adj)


def main(n_charts: int = 5, n_players: int = 120):
    client = PhiraClient()

    # harvest player ids from charts' record pages
    players = []
    seen = set()
    for meta in list(_few_charts(client, n_charts)):
        for r in client.iter_chart_records(meta, max_records=30):
            if r.player not in seen:
                seen.add(r.player)
                players.append(r.player)
            if len(players) >= n_players:
                break
        if len(players) >= n_players:
            break
    print(f"harvested {len(players)} players")

    edges = []
    per_player = []
    for i, pid in enumerate(players):
        try:
            pool = client.get_best_pool(pid)
        except Exception:  # noqa: BLE001
            continue
        rows = pool.get("bestPool", pool if isinstance(pool, list) else [])
        charts = {row.get("chart") for row in rows if row.get("chart") is not None}
        per_player.append(len(charts))
        for c in charts:
            edges.append((pid, c))
        if (i + 1) % 40 == 0:
            print(f"  fetched {i+1}/{len(players)} pools")

    import numpy as np
    pp = np.asarray(per_player)
    print(f"pools fetched: {len(per_player)}")
    if pp.size:
        print(f"charts per player: mean={pp.mean():.1f} median={np.median(pp):.0f} "
              f"min={pp.min()} max={pp.max()}")
    n_components = len({c for _, c in edges})
    print(f"edges={len(edges)} distinct charts={n_components}")
    best, total_nodes = connected_components(edges)
    print(f"largest connected component: {best} nodes of {total_nodes} total "
          f"({best/total_nodes if total_nodes else 0:.1%})")


def _few_charts(client, n):
    from phira_pp.api import _meta_from_dict

    page = 1
    got = 0
    while got < n:
        data = client.search_charts(page=page, pageNum=30, order="rating", division="regular")
        rows = data.get("results") or data.get("result") or []
        if not rows:
            break
        for row in rows:
            meta = _meta_from_dict(row)
            if meta.ranked and meta.reviewed and meta.rating_count >= 200:
                yield meta.id
                got += 1
                if got >= n:
                    return
        page += 1


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 5,
         int(sys.argv[2]) if len(sys.argv) > 2 else 120)
