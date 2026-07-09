"""Quality layer for eval_metrics: property-based tests (invariants that must hold for ANY
input), metamorphic tests (relations that must hold between related inputs), and targeted
example tests that each kill a specific surviving mutant from the baseline mutmut run.

This file ADDS to tests/test_eval_metrics.py (the hand-picked examples); it does not replace it.
Run mutation testing with:  python -m mutmut run   (config in pyproject.toml [tool.mutmut])
"""
from __future__ import annotations

from hypothesis import given, settings, strategies as st

from graph_guard.eval_metrics import evaluate, lift, _FAMILIES, _NUMERIC_METRICS
from graph_guard.eval_probes import Probe


# ── a strategy that builds a (fake arm, probes) pair ────────────────────────────────────────
# Each probe gets a unique query; the arm is a lookup from query -> ranked id list. gold_id is
# either one of the ranked ids (a hit at some rank) or a guaranteed-absent id (a miss).
_ids = st.text(alphabet="abcdefgh", min_size=1, max_size=3)


@st.composite
def _probe_sets(draw):
    n = draw(st.integers(min_value=1, max_value=8))
    mapping: dict = {}
    probes = []
    for i in range(n):
        q = f"q{i}"
        ranked = draw(st.lists(_ids, min_size=0, max_size=6, unique=True))
        fam = draw(st.sampled_from(list(_FAMILIES)))
        if ranked and draw(st.booleans()):
            gold = draw(st.sampled_from(ranked))          # a hit
        else:
            gold = f"ABSENT_{i}"                           # uppercase -> never in lowercase ranked
        mapping[q] = ranked
        probes.append(Probe(family=fam, query=q, gold_id=gold))

    def arm(query, k, _m=mapping):
        return [{"id": x} for x in _m.get(query, [])][:k]

    return arm, probes


def _numeric(group: dict):
    """Yield the numeric metric values that are actually present and not guarded-off (None)."""
    for key in ("hit@1", "hit@5", "hit@10", "mrr"):
        v = group.get(key)
        if v is not None:
            yield key, v


# ══ PILLAR 1 — PROPERTY-BASED TESTS (invariants true for every input) ════════════════════════

@given(_probe_sets())
@settings(max_examples=300)
def test_all_scores_in_unit_interval(data):
    """Every hit@k and mrr the module ever reports is a fraction in [0, 1] (or guarded None)."""
    arm, probes = data
    result = evaluate(arm, probes, k=10)
    for group in result.values():
        for _key, v in _numeric(group):
            assert 0.0 <= v <= 1.0


@given(_probe_sets())
@settings(max_examples=300)
def test_hit_at_k_is_monotonic(data):
    """hit@1 <= hit@5 <= hit@10: a wider cutoff can only catch more golds, never fewer."""
    arm, probes = data
    result = evaluate(arm, probes, k=10)
    for group in result.values():
        assert group["hit@1"] <= group["hit@5"] <= group["hit@10"]


@given(_probe_sets())
@settings(max_examples=300)
def test_n_counts_every_probe(data):
    """overall n equals the probe count; each family n equals its share; the parts sum to the whole."""
    arm, probes = data
    result = evaluate(arm, probes, k=10)
    assert result["overall"]["n"] == len(probes)
    assert sum(result[fam]["n"] for fam in _FAMILIES) == len(probes)


@given(st.lists(st.sampled_from(list(_FAMILIES)), min_size=1, max_size=6))
def test_perfect_arm_scores_one(families):
    """If the arm always returns gold at rank 1, every score must be a perfect 1.0."""
    mapping = {f"q{i}": f"gold{i}" for i in range(len(families))}
    probes = [Probe(family=f, query=f"q{i}", gold_id=f"gold{i}") for i, f in enumerate(families)]
    arm = lambda q, k, _m=mapping: [{"id": _m[q]}][:k]

    result = evaluate(arm, probes, k=10)
    assert result["overall"]["hit@1"] == 1.0
    assert result["overall"]["hit@10"] == 1.0
    assert result["overall"]["mrr"] == 1.0


@given(_probe_sets())
@settings(max_examples=200)
def test_gold_never_present_scores_zero(data):
    """Force every gold to be absent: all hits and mrr must be exactly 0.0."""
    arm, probes = data
    absent = [Probe(family=p.family, query=p.query, gold_id=f"NEVER_{i}") for i, p in enumerate(probes)]
    result = evaluate(arm, absent, k=10)
    assert result["overall"]["hit@10"] == 0.0
    assert result["overall"]["mrr"] == 0.0


# ══ PILLAR 2 — METAMORPHIC TESTS (relations between related inputs) ═══════════════════════════

@given(_probe_sets())
@settings(max_examples=300)
def test_probe_order_does_not_matter(data):
    """Aggregates are order-invariant: shuffling the probe list cannot change the metrics."""
    arm, probes = data
    forward = evaluate(arm, probes, k=10)
    backward = evaluate(arm, list(reversed(probes)), k=10)
    assert forward == backward


def test_lift_is_antisymmetric():
    """lift(A, B) == -lift(B, A) for every numeric metric (a delta flips sign when reversed)."""
    a = {"overall": {"hit@1": 0.6, "hit@5": 0.8, "hit@10": 0.9, "mrr": 0.65}}
    b = {"overall": {"hit@1": 0.5, "hit@5": 0.7, "hit@10": 0.85, "mrr": 0.6}}
    ab = lift(a, b)
    ba = lift(b, a)
    for metric in _NUMERIC_METRICS:
        assert ab["overall"][metric] == -ba["overall"][metric]


def test_self_lift_is_zero():
    """lift(A, A) is 0 for every numeric metric: an arm has no lift over itself."""
    a = {"multi_hop": {"hit@1": 0.4, "hit@5": 0.7, "hit@10": 0.8, "mrr": 0.5}}
    result = lift(a, a)
    for metric in _NUMERIC_METRICS:
        assert result["multi_hop"][metric] == 0.0


# ══ TARGETED KILLS — each test below dispatches a specific baseline survivor ══════════════════

def test_default_k_is_10():
    """Kills evaluate mutant #1 (default k 10 -> 11). Gold sits at rank 11: reachable only if the
    default k were 11. With the real default (10) it is out of reach, so mrr must be 0.0."""
    ranked = [f"n{i}" for i in range(10)] + ["gold"]        # gold at rank 11
    arm = lambda q, k: [{"id": x} for x in ranked][:k]
    probes = [Probe(family="multi_hop", query="q", gold_id="gold")]

    result = evaluate(arm, probes)                          # no k -> exercises the default
    assert result["multi_hop"]["hit@10"] == 0.0
    assert result["multi_hop"]["mrr"] == 0.0


def test_evaluate_passes_k_through_to_the_arm():
    """Kills evaluate mutant #7 (arm called with None instead of k). At k=3 the arm must be asked
    for only 3 results, so gold at rank 5 is truncated away and mrr is 0.0. If k were dropped
    (None), the arm would return all 5 and gold would leak in."""
    ranked = ["a", "b", "c", "d", "gold"]                   # gold at rank 5
    arm = lambda q, k: [{"id": x} for x in ranked][:k]
    probes = [Probe(family="multi_hop", query="q", gold_id="gold")]

    result = evaluate(arm, probes, k=3)
    assert result["multi_hop"]["mrr"] == 0.0


def test_unknown_family_does_not_crash():
    """Kills evaluate mutants #20 / #22 (setdefault default []-> None / dropped). A probe whose
    family is outside _FAMILIES must still be counted in 'overall' without an AttributeError."""
    arm = lambda q, k: [{"id": "gold"}][:k]
    probes = [Probe(family="mystery", query="q", gold_id="gold")]

    result = evaluate(arm, probes, k=10)
    assert result["overall"]["n"] == 1
    assert result["overall"]["hit@1"] == 1.0


def test_lift_survives_missing_baseline_group():
    """Kills lift mutants #4 / #6 (baseline.get default {} -> None / dropped). A group present in
    the arm but absent from the baseline must yield None deltas, not a crash."""
    arm = {"overall": {"hit@1": 0.5, "hit@5": 0.7, "hit@10": 0.8, "mrr": 0.6}}
    result = lift(arm, {})                                  # 'overall' missing from baseline
    assert result["overall"]["hit@1"] is None
    assert result["overall"]["mrr"] is None


def test_lift_survives_one_sided_none_metric():
    """Kills lift mutant #13 (the None guard's 'or' -> 'and'). When exactly ONE side's metric is
    None (e.g. an arm run at k=3 vs a baseline run at k=10), the delta must be None, never an
    attempted None - number subtraction."""
    arm = {"multi_hop": {"hit@1": 0.5, "hit@5": None, "hit@10": None, "mrr": 0.4}}
    base = {"multi_hop": {"hit@1": 0.5, "hit@5": 0.8, "hit@10": 0.9, "mrr": 0.4}}

    result = lift(arm, base)
    assert result["multi_hop"]["hit@5"] is None            # a=None, b=0.8 -> None
    assert result["multi_hop"]["hit@1"] == 0.0


# ── NO SURVIVING MUTANTS ─────────────────────────────────────────────────────────────────────
# `python -m mutmut run` now leaves zero survivors: 108 mutants, 108 killed.
#
# It used to leave two. `evaluate` read `ranks_by_family.get(fam, [])`, and mutants #37/#39
# altered that `[]` default. They were correctly identified as EQUIVALENT — `ranks_by_family` is
# initialized as {fam: [] for fam in _FAMILIES} and read back over the same tuple, so the key is
# always present and the default is unreachable — and then left alive on the reasoning that no
# test could distinguish them.
#
# That reasoning was sound and the remedy was wrong. An unreachable default is dead code, and it
# quietly tells the next reader that a family can be missing when none ever can. Deleting it
# removes the equivalence class entirely, which beats documenting it forever: the survivors did
# not get excused, they stopped existing. `evaluate` now indexes directly.
#
# The general rule, learned the same way in oracle-gate: if nothing can test it, ask why it is
# there. Untestable code is usually a design problem announcing itself, not a testing problem.

