from graph_guard.ppr import personalized_pagerank
from graph_guard.reasoned_graph import reasoned_adjacency
from graph_guard.store import TripleStore


def _chain_store():
    """A -supersedes-> B -supersedes-> C. Only single-hop edges are asserted; the raw
    store never gets an A-C edge -- only owlrl's supersedesTransitively closure does."""
    s = TripleStore()
    for node_id in ("A", "B", "C"):
        s.upsert_node({"id": node_id, "type": "Project", "name": f"Project {node_id}"})
    s.upsert_edge({"src": "A", "predicate": "supersedes", "dst": "B"})
    s.upsert_edge({"src": "B", "predicate": "supersedes", "dst": "C"})
    return s


def test_entailed_transitive_edge_present():
    s = _chain_store()
    raw = s.adjacency()
    reasoned = reasoned_adjacency(s)

    assert "C" not in raw.get("A", {})
    assert "A" not in raw.get("C", {})

    assert "C" in reasoned["A"]
    assert "A" in reasoned["C"]


def test_symmetric():
    s = _chain_store()
    reasoned = reasoned_adjacency(s)

    assert reasoned  # sanity: non-empty
    for a, nbrs in reasoned.items():
        for b, w in nbrs.items():
            assert reasoned[b][a] == w


def test_external_class_edges_excluded():
    """Entailed rdf:type schema:Project typing must never surface as a graph edge --
    every adjacency key/neighbor must be a real note id, never a class IRI/id."""
    s = _chain_store()
    reasoned = reasoned_adjacency(s)
    note_ids = {n["id"] for n in s.all_nodes()}

    for a, nbrs in reasoned.items():
        assert a in note_ids
        for b in nbrs:
            assert b in note_ids


def test_reification_not_edges():
    """The rdf:Statement provenance/confidence reification blocks rdf_export emits per
    edge must never create note<->note adjacency beyond the real asserted/entailed ones."""
    s = _chain_store()
    reasoned = reasoned_adjacency(s)

    # Only the asserted A-B, B-C edges plus the entailed A-C closure should exist --
    # nothing extra leaking in from the rdf:Statement/rdf:subject/predicate/object blocks.
    assert set(reasoned.keys()) == {"A", "B", "C"}
    assert set(reasoned["A"]) == {"B", "C"}
    assert set(reasoned["B"]) == {"A", "C"}
    assert set(reasoned["C"]) == {"A", "B"}


def test_dangling_edge_endpoint_excluded():
    """An edge naming a src/dst id that was never registered via upsert_node (so it's
    absent from store.all_nodes()) must not surface as an adjacency edge -- confirms
    the id-membership guard, not just IRI shape, decides real-note-ness."""
    s = TripleStore()
    s.upsert_node({"id": "A", "type": "Project", "name": "Project A"})
    # "ghost"/"ghost2" are never upserted as nodes -- store.all_nodes() never includes them.
    s.upsert_edge({"src": "A", "predicate": "mentions", "dst": "ghost"})
    s.upsert_edge({"src": "ghost2", "predicate": "mentions", "dst": "A"})

    reasoned = reasoned_adjacency(s)

    assert reasoned.get("A", {}) == {}
    assert "ghost" not in reasoned
    assert "ghost2" not in reasoned


def test_type_cohort_off_by_default_on_when_asked():
    s = TripleStore()
    s.upsert_node({"id": "P1", "type": "Project", "name": "Project One"})
    s.upsert_node({"id": "P2", "type": "Project", "name": "Project Two"})
    # no relation between P1 and P2 at all

    off = reasoned_adjacency(s)
    assert "P2" not in off.get("P1", {})
    assert "P1" not in off.get("P2", {})

    on = reasoned_adjacency(s, type_cohort=True)
    assert "P2" in on["P1"]
    assert "P1" in on["P2"]


def test_shape_matches_adjacency():
    s = _chain_store()
    reasoned = reasoned_adjacency(s)

    assert isinstance(reasoned, dict)
    for node, nbrs in reasoned.items():
        assert isinstance(node, str)
        assert isinstance(nbrs, dict)
        for neighbor, weight in nbrs.items():
            assert isinstance(neighbor, str)
            assert isinstance(weight, float)

    scores = personalized_pagerank(reasoned, ["A"])
    assert isinstance(scores, dict)
    assert scores  # non-empty
    assert all(isinstance(v, float) for v in scores.values())
