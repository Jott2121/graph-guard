from graph_guard.eval_metrics import evaluate, lift
from graph_guard.eval_probes import Probe


def _arm(mapping):
    """Tiny fake arm: query -> fixed ranked id list. Matches the real arm_fn(query, k) ->
    [{"id": ...}, ...] shape (GraphRetriever.retrieve / tfidf_fn)."""
    def fn(query, k):
        return [{"id": nid} for nid in mapping.get(query, [])][:k]
    return fn


def test_hit_and_mrr_exact():
    arm = _arm({"solo": ["a", "b", "gold", "d"]})  # gold at rank 3
    probes = [Probe(family="multi_hop", query="solo", gold_id="gold")]

    result = evaluate(arm, probes, k=10)
    fam = result["multi_hop"]
    assert fam["hit@1"] == 0.0
    assert fam["hit@5"] == 1.0
    assert fam["hit@10"] == 1.0
    assert fam["mrr"] == round(1 / 3, 4)
    assert fam["n"] == 1
    assert result["overall"] == fam

    # a second probe with gold at rank 1 -- averages must update correctly
    arm2 = _arm({
        "solo": ["a", "b", "gold", "d"],
        "first": ["gold2", "x"],
    })
    probes2 = [
        Probe(family="multi_hop", query="solo", gold_id="gold"),
        Probe(family="multi_hop", query="first", gold_id="gold2"),
    ]

    result2 = evaluate(arm2, probes2, k=10)
    fam2 = result2["multi_hop"]
    assert fam2["hit@1"] == 0.5
    assert fam2["hit@5"] == 1.0
    assert fam2["hit@10"] == 1.0
    assert fam2["mrr"] == round((1 / 3 + 1.0) / 2, 4)
    assert fam2["n"] == 2


def test_gold_absent():
    arm = _arm({"q": ["a", "b", "c"]})
    probes = [Probe(family="simple_lookup", query="q", gold_id="missing")]

    result = evaluate(arm, probes, k=10)
    fam = result["simple_lookup"]
    assert fam["hit@1"] == 0.0
    assert fam["hit@5"] == 0.0
    assert fam["hit@10"] == 0.0
    assert fam["mrr"] == 0.0
    assert fam["n"] == 1


def test_per_family_split():
    arm = _arm({
        "mh": ["x", "gold_mh"],       # rank 2
        "sl": ["gold_sl", "y"],       # rank 1
    })
    probes = [
        Probe(family="multi_hop", query="mh", gold_id="gold_mh"),
        Probe(family="simple_lookup", query="sl", gold_id="gold_sl"),
    ]

    result = evaluate(arm, probes, k=10)

    assert result["multi_hop"]["n"] == 1
    assert result["multi_hop"]["hit@1"] == 0.0
    assert result["multi_hop"]["hit@5"] == 1.0
    assert result["multi_hop"]["mrr"] == 0.5

    assert result["simple_lookup"]["n"] == 1
    assert result["simple_lookup"]["hit@1"] == 1.0
    assert result["simple_lookup"]["mrr"] == 1.0

    assert result["overall"]["n"] == 2
    assert result["overall"]["hit@1"] == 0.5
    assert result["overall"]["mrr"] == round((0.5 + 1.0) / 2, 4)


def test_empty_family_no_crash():
    arm = _arm({"sl": ["gold_sl"]})
    probes = [Probe(family="simple_lookup", query="sl", gold_id="gold_sl")]

    result = evaluate(arm, probes, k=10)

    assert result["multi_hop"] == {"hit@1": 0.0, "hit@5": 0.0, "hit@10": 0.0, "mrr": 0.0, "n": 0}
    assert result["simple_lookup"]["n"] == 1


def test_lift_deltas():
    arm_metrics = {
        "overall": {"hit@1": 0.6, "hit@5": 0.8, "hit@10": 0.9, "mrr": 0.65, "n": 10},
        "multi_hop": {"hit@1": 0.4, "hit@5": 0.7, "hit@10": 0.8, "mrr": 0.5, "n": 5},
        "simple_lookup": {"hit@1": 0.8, "hit@5": 0.9, "hit@10": 1.0, "mrr": 0.85, "n": 5},
    }
    baseline_metrics = {
        "overall": {"hit@1": 0.5, "hit@5": 0.7, "hit@10": 0.85, "mrr": 0.6, "n": 10},
        # arm is WORSE than baseline here -- deltas must come back negative, reported straight
        "multi_hop": {"hit@1": 0.5, "hit@5": 0.75, "hit@10": 0.85, "mrr": 0.55, "n": 5},
        "simple_lookup": {"hit@1": 0.8, "hit@5": 0.9, "hit@10": 1.0, "mrr": 0.85, "n": 5},
    }

    result = lift(arm_metrics, baseline_metrics)

    assert result["overall"]["hit@1"] == round(0.6 - 0.5, 4)
    assert result["overall"]["hit@5"] == round(0.8 - 0.7, 4)
    assert result["overall"]["hit@10"] == round(0.9 - 0.85, 4)
    assert result["overall"]["mrr"] == round(0.65 - 0.6, 4)

    assert result["multi_hop"]["hit@1"] == round(0.4 - 0.5, 4) == -0.1
    assert result["multi_hop"]["mrr"] == round(0.5 - 0.55, 4) == -0.05

    assert result["simple_lookup"]["hit@1"] == 0.0
    assert result["simple_lookup"]["mrr"] == 0.0

    # lift is a per-metric delta, not a probe count -- n is not a "numeric metric" to diff
    assert "n" not in result["overall"]


def test_k_below_10_guards_higher_cutoffs():
    # k=3: the arm never retrieves past rank 3, so hit@5/hit@10 would just restate hit@3
    # under a misleading label -- guarded off as None instead of a fabricated number.
    arm = _arm({"q": ["a", "b", "gold"]})  # gold at rank 3, within k=3
    probes = [Probe(family="multi_hop", query="q", gold_id="gold")]

    result = evaluate(arm, probes, k=3)
    fam = result["multi_hop"]
    assert fam["hit@1"] == 0.0
    assert fam["hit@5"] is None
    assert fam["hit@10"] is None
    assert fam["mrr"] == round(1 / 3, 4)

    # lift must not raise when one side has a guarded-off None metric
    guarded_lift = lift({"multi_hop": fam}, {"multi_hop": fam})
    assert guarded_lift["multi_hop"]["hit@5"] is None
