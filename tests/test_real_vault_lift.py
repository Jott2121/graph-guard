"""Tests for eval.real_vault_lift's 3-arm harness. SYNTHETIC fixture only -- these tests must
NEVER read Jeff's private vault. Every note here is crafted by hand so build_graph's real
extraction pipeline (frontmatter / wikilinks / inline relation cues) yields a genuine
'supersedes' edge between two notes whose clean labels share no words, exercising the exact
multi-hop case the graph arm exists to win."""
from __future__ import annotations

import json

from eval.real_vault_lift import run


def _write_vault(vault_dir):
    """Apex Protocol supersedes Legacy Ledger via an inline wikilink cue in the body (real
    extraction, not a hand-built store) -- 'apex protocol' and 'legacy ledger' share zero
    tokens, so flat lexical retrieval for the query 'apex protocol' cannot find Legacy Ledger
    by word overlap; only the graph edge reaches it. F0-F3 are unrelated filler notes (no
    edges, no shared vocabulary with either note) that give flat retrieval enough competing
    zero-score candidates to actually push Legacy Ledger out of a small top-k."""
    (vault_dir / "Apex Protocol.md").write_text(
        "# Apex Protocol\n\nThis project supersedes [[Legacy Ledger]] going forward.\n"
    )
    (vault_dir / "Legacy Ledger.md").write_text(
        "# Legacy Ledger\n\nAn archived record of the old bookkeeping process, now retired.\n"
    )
    fillers = {
        "F0 Notes.md": "Some thoughts about gardening and rainfall patterns this spring.",
        "F1 Notes.md": "A quick recipe for sourdough bread with notes on hydration ratios.",
        "F2 Notes.md": "Travel planning ideas for a weekend trip to the coast.",
        "F3 Notes.md": "A short list of movies to watch this weekend with friends.",
    }
    for name, body in fillers.items():
        (vault_dir / name).write_text(f"# {name[:-3]}\n\n{body}\n")
    return vault_dir


def _fixture(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    return _write_vault(vault)


def test_run_shape(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    vault = _fixture(tmp_path)

    result = run(roots=[str(vault)])

    assert set(result) == {"vault", "probes", "k", "arms", "lift"}
    assert set(result["vault"]) == {"nodes", "edges", "notes"}
    assert result["vault"]["notes"] == 6
    assert result["vault"]["edges"] == 1

    assert set(result["probes"]) == {"multi_hop", "simple_lookup", "discarded", "capped"}
    assert result["probes"]["multi_hop"] == 1
    assert result["probes"]["simple_lookup"] == 6
    assert result["probes"]["capped"] is False

    assert result["k"] == 10

    assert set(result["arms"]) == {"flat", "graph", "reasoned"}
    for arm in result["arms"].values():
        assert set(arm) == {"overall", "multi_hop", "simple_lookup"}
        for family_metrics in arm.values():
            assert set(family_metrics) == {"hit@1", "hit@5", "hit@10", "mrr", "n"}

    assert set(result["lift"]) == {"graph_vs_flat", "reasoned_vs_flat", "reasoned_vs_graph"}
    for lift_group in result["lift"].values():
        assert set(lift_group) == {"overall", "multi_hop", "simple_lookup"}


def test_graph_beats_flat_on_constructed_multihop(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    vault = _fixture(tmp_path)

    # k=5 with 4 filler notes: flat's top-5 is Apex + the 4 zero-score fillers -- Legacy
    # Ledger (also zero-score lexically) is pushed just outside it. The graph arm's PPR hop
    # over the supersedes edge lifts Legacy Ledger's fused score well above the fillers'.
    result = run(roots=[str(vault)], k=5)

    flat_mh = result["arms"]["flat"]["multi_hop"]
    graph_mh = result["arms"]["graph"]["multi_hop"]
    reasoned_mh = result["arms"]["reasoned"]["multi_hop"]

    assert flat_mh["n"] == 1
    assert flat_mh["hit@5"] == 0.0
    assert graph_mh["hit@5"] == 1.0
    assert reasoned_mh["hit@5"] == 1.0
    assert graph_mh["hit@5"] > flat_mh["hit@5"]
    assert reasoned_mh["hit@5"] > flat_mh["hit@5"]


def test_caps_truncate_and_flag_capped(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    vault = _fixture(tmp_path)

    result = run(roots=[str(vault)], max_multihop=0, max_simple=2)

    assert result["probes"]["multi_hop"] == 0
    assert result["probes"]["simple_lookup"] == 2
    assert result["probes"]["capped"] is True


def test_caps_above_actual_count_not_flagged_capped(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    vault = _fixture(tmp_path)

    result = run(roots=[str(vault)], max_multihop=100, max_simple=100)

    assert result["probes"]["multi_hop"] == 1
    assert result["probes"]["simple_lookup"] == 6
    assert result["probes"]["capped"] is False


def test_results_json_written(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    vault = _fixture(tmp_path)

    result = run(roots=[str(vault)])

    results_path = tmp_path / "eval" / "results.json"
    assert results_path.exists()
    with open(results_path) as f:
        loaded = json.load(f)
    assert loaded == result


def test_results_are_pii_free(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    vault = _fixture(tmp_path)

    result = run(roots=[str(vault)])
    serialized = json.dumps(result)

    banned = [
        "/", ".md", str(tmp_path), str(vault),
        "Apex", "apex", "Protocol", "protocol",
        "Legacy", "legacy", "Ledger", "ledger",
        "F0 Notes", "F1 Notes", "F2 Notes", "F3 Notes",
        "gardening", "sourdough", "bookkeeping",
        "supersedes",
    ]
    for token in banned:
        assert token not in serialized, f"leak found in results: {token!r}"
