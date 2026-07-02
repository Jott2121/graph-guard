from eval.sparql_vs_ppr import KNOWN_SUPERSEDED, _print_comparison, run


def test_sparql_closure_is_exactly_the_known_superseded_set():
    """The property-path route (no reasoner) returns the exact, deterministic closure --
    not more, not less -- regardless of the noise nodes also present in the fixture."""
    r = run()
    assert set(r["sparql"]["property_path_closure"]) == KNOWN_SUPERSEDED


def test_sparql_entailment_route_agrees_with_property_path():
    """owlrl materialization entails kl:supersedesTransitively for exactly the same set the
    property path finds -- two independent SPARQL/OWL routes converging on one answer."""
    r = run()
    sparql = r["sparql"]
    assert set(sparql["entailed_supersedes_transitively"]) == KNOWN_SUPERSEDED
    assert set(sparql["property_path_on_reasoned_graph"]) == KNOWN_SUPERSEDED


def test_pagerank_returns_nonempty_ranked_result_seeded_on_start():
    """Structure only -- not exact scores (fragile): the real PPR entry point
    (GraphRetriever.retrieve) must link the query to the start node and return a
    non-empty ranked list that includes it."""
    r = run()
    pagerank = r["pagerank"]
    assert r["start"] in pagerank["seeds"]
    assert len(pagerank["ranked"]) > 0
    ids = pagerank["ranked_ids"]
    assert r["start"] in ids
    assert all(isinstance(hit["score"], float) for hit in pagerank["ranked"])
    # ranked list must be sorted by descending score (it's a RANKING, not a set)
    scores = [hit["score"] for hit in pagerank["ranked"]]
    assert scores == sorted(scores, reverse=True)


def test_pagerank_surfaces_noise_nodes_not_in_the_supersedes_closure():
    """The demo fixture is only useful if PageRank actually diffuses onto the noise nodes
    (connected by `mentions`/`related`, not `supersedes`) -- proving the two engines can
    visibly differ on the SAME fixture, which is the whole point of the comparison."""
    r = run()
    ranked_ids = set(r["pagerank"]["ranked_ids"])
    noise_ids = ranked_ids - KNOWN_SUPERSEDED - {r["start"]}
    assert noise_ids, "fixture must produce at least one PageRank hit outside the exact SPARQL closure"


def test_disconnected_node_absent_from_both_results():
    """The fully disconnected control node (project_unrelated.md) must not appear in either
    engine's result -- confirms neither method spuriously surfaces an unrelated node."""
    r = run()
    assert "project_unrelated.md" not in r["sparql"]["property_path_closure"]
    assert "project_unrelated.md" not in r["pagerank"]["ranked_ids"]


def test_print_comparison_labels_both_engines(capsys):
    """The stdout report (what docs/SPARQL-vs-PPR.md's real-output section is pasted from)
    clearly labels the exact SPARQL closure and the ranked PageRank list, and flags the noise
    nodes PageRank surfaces that are not in the known superseded set."""
    r = run()
    _print_comparison(r)
    out = capsys.readouterr().out
    assert "SPARQL / OWL (Tier B)" in out
    assert "Personalized PageRank (Tier A)" in out
    for node_id in KNOWN_SUPERSEDED:
        assert node_id in out
    assert "KNOWN SUPERSEDED" in out
    assert "noise (not superseded)" in out


def test_print_comparison_handles_no_noise_case(capsys):
    """Defensive branch: if a result happened to contain zero noise nodes above the known set,
    the report still prints a coherent (non-crashing) interpretation line instead of the
    noise-listing branch."""
    r = run()
    r["pagerank"]["ranked"] = [
        {"id": node_id, "text": node_id, "score": 1.0} for node_id in KNOWN_SUPERSEDED
    ] + [{"id": r["start"], "text": r["start"], "score": 1.0}]
    _print_comparison(r)
    out = capsys.readouterr().out
    assert "happened to contain no noise nodes" in out


def test_run_is_reproducible_modulo_timing():
    """Two runs of the fixture must agree on every substantive field -- only the *_ms timing
    fields are expected to vary run to run."""
    r1, r2 = run(), run()
    for key in ("query", "start", "known_superseded"):
        assert r1[key] == r2[key]
    for key in ("property_path_closure", "entailed_supersedes_transitively", "property_path_on_reasoned_graph"):
        assert r1["sparql"][key] == r2["sparql"][key]
    for key in ("seeds", "ranked", "ranked_ids"):
        assert r1["pagerank"][key] == r2["pagerank"][key]
