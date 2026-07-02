"""Personalized PageRank over a weighted adjacency dict — stdlib only.

HippoRAG-style single-shot multi-hop retrieval: seed on query-linked nodes and let PPR
diffuse relevance across typed edges. NetworkX is an optional drop-in (pyproject [graph])."""
from __future__ import annotations

import math


def personalized_pagerank(adj, seeds, *, alpha=0.85, iters=50, tol=1e-9):
    """adj: {node: {neighbor: weight}}. seeds: iterable of node ids to personalize toward.
    Returns {node: score} summing to ~1. Absent seeds -> plain PageRank (uniform teleport)."""
    nodes = set(adj)
    for nbrs in adj.values():
        nodes.update(nbrs)
    if not nodes:
        return {}
    valid = [s for s in seeds if s in nodes]
    if not valid:
        valid = list(nodes)
    tele = {}
    for s in valid:
        tele[s] = tele.get(s, 0.0) + 1.0 / len(valid)
    n = len(nodes)
    rank = {v: 1.0 / n for v in nodes}
    out_sum = {u: sum(adj.get(u, {}).values()) for u in nodes}
    for _ in range(iters):
        nxt = {v: 0.0 for v in nodes}
        dangling = 0.0
        for u in nodes:
            ru = rank[u]
            s = out_sum.get(u, 0.0)
            if s <= 0:
                dangling += ru
                continue
            for v, w in adj.get(u, {}).items():
                nxt[v] += alpha * ru * (w / s)
        mass = (1.0 - alpha) + alpha * dangling
        for sd, p in tele.items():
            nxt[sd] += mass * p
        delta = sum(abs(nxt[v] - rank[v]) for v in nodes)
        rank = nxt
        if delta < tol:
            break
    return rank


def node_specificity(adj):
    """Down-weight high-degree generic hubs (IDF analogue): {node: 1/(1+log(1+degree))}.
    adjacency() is symmetric, so each node's own row already holds its full degree."""
    return {u: 1.0 / (1.0 + math.log(1.0 + len(nbrs))) for u, nbrs in adj.items()}
