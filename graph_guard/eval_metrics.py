"""Ranking metrics for the Gate D retrieval-lift eval: hit@1/5/10 + MRR per probe family and
overall, plus lift (delta between two arms' metrics). Pure arithmetic over ranked id lists --
no dependencies, no I/O, deterministic. Does not assume any specific arm implementation: an
"arm" is any `arm_fn(query: str, k: int) -> list[dict]` where each dict has an "id" key (the
shape shared by `GraphRetriever.retrieve` and the flat `tfidf_fn`)."""
from __future__ import annotations

# The two probe families produced by `graph_guard.eval_probes`. Fixed (not derived from the
# probes passed in) so a family with zero probes in a given run still gets a real, zeroed
# entry in the output -- never a missing key / KeyError downstream.
_FAMILIES = ("multi_hop", "simple_lookup")
_CUTOFFS = (1, 5, 10)
_NUMERIC_METRICS = ("hit@1", "hit@5", "hit@10", "mrr")
_ROUND = 4


def _empty_group() -> dict:
    return {"hit@1": 0.0, "hit@5": 0.0, "hit@10": 0.0, "mrr": 0.0, "n": 0}


def _rank(ranked_ids: list, gold_id) -> int | None:
    """1-based position of gold_id in ranked_ids, or None if absent."""
    try:
        return ranked_ids.index(gold_id) + 1
    except ValueError:
        return None


def _score_group(ranks: list, k: int) -> dict:
    """ranks: one entry per probe in the group (int rank or None). k: the cutoff the arm was
    actually run at -- ranks can never exceed k, so hit@N for N > k would just restate hit@k
    under a misleading label; guarded off (reported as None) instead."""
    n = len(ranks)
    if n == 0:
        return _empty_group()
    group: dict = {"n": n}
    for cutoff in _CUTOFFS:
        if cutoff <= k:
            hits = sum(1 for r in ranks if r is not None and r <= cutoff)
            group[f"hit@{cutoff}"] = round(hits / n, _ROUND)
        else:
            # documented guard: N > k is not meaningful (arm never retrieved that deep)
            group[f"hit@{cutoff}"] = None
    rr_sum = sum((1.0 / r) if r else 0.0 for r in ranks)
    group["mrr"] = round(rr_sum / n, _ROUND)
    return group


def evaluate(arm_fn, probes, *, k: int = 10) -> dict:
    """Run `arm_fn` over every probe, find the 1-based rank of each probe's gold_id in the
    returned ranked ids, and aggregate hit@1/5/10 + MRR both per-family and overall."""
    ranks_by_family: dict = {fam: [] for fam in _FAMILIES}
    overall_ranks: list = []
    for probe in probes:
        hits = arm_fn(probe.query, k) or []
        ranked_ids = [h["id"] for h in hits]
        r = _rank(ranked_ids, probe.gold_id)
        ranks_by_family.setdefault(probe.family, []).append(r)
        overall_ranks.append(r)

    result = {"overall": _score_group(overall_ranks, k)}
    for fam in _FAMILIES:
        result[fam] = _score_group(ranks_by_family.get(fam, []), k)
    return result


def lift(arm_metrics: dict, baseline_metrics: dict) -> dict:
    """Per-family, per-metric absolute delta (arm - baseline) for hit@1/5/10/mrr. Deltas are
    reported straight, including negative ones when the arm is worse than the baseline. `n`
    (a probe count, not a score) is not diffed. A cutoff guarded off as None (N > k) stays
    None in the delta rather than raising."""
    result: dict = {}
    for group, arm_group in arm_metrics.items():
        base_group = baseline_metrics.get(group, {})
        deltas = {}
        for metric in _NUMERIC_METRICS:
            a = arm_group.get(metric)
            b = base_group.get(metric)
            deltas[metric] = None if a is None or b is None else round(a - b, _ROUND)
        result[group] = deltas
    return result
