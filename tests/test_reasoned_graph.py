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


def test_asserted_edge_confidence_preserved():
    """The reasoned arm (A3) must equal the graph arm (A2) PLUS reasoning-revealed edges --
    it may never re-weight an asserted edge. An asserted supersedes edge at confidence 0.5
    stays 0.5: not flattened to 1.0, and not inflated by the entailed supersedesTransitively
    edge that owlrl derives on the SAME A-B pair."""
    s = TripleStore()
    s.upsert_node({"id": "A", "type": "Project", "name": "Project A"})
    s.upsert_node({"id": "B", "type": "Project", "name": "Project B"})
    s.upsert_edge({"src": "A", "predicate": "supersedes", "dst": "B", "confidence": 0.5})

    raw = s.adjacency()
    reasoned = reasoned_adjacency(s)

    assert raw["A"]["B"] == 0.5
    assert reasoned["A"]["B"] == raw["A"]["B"] == 0.5
    assert reasoned["B"]["A"] == raw["B"]["A"] == 0.5


def test_new_entailed_edge_weight_is_one():
    """A genuinely-new entailed edge carries a uniform weight of exactly 1.0, independent of
    the confidence of the asserted edges it was derived from."""
    s = TripleStore()
    for node_id in ("A", "B", "C"):
        s.upsert_node({"id": node_id, "type": "Project", "name": f"Project {node_id}"})
    s.upsert_edge({"src": "A", "predicate": "supersedes", "dst": "B", "confidence": 0.5})
    s.upsert_edge({"src": "B", "predicate": "supersedes", "dst": "C", "confidence": 0.5})

    reasoned = reasoned_adjacency(s)

    assert reasoned["A"]["B"] == 0.5  # asserted weight preserved
    # A-C is derivable ONLY by the transitive closure -> new entailed edge, weight 1.0
    # (not 0.5 inherited from the chain, not 2.0 from a double add).
    assert reasoned["A"]["C"] == 1.0
    assert reasoned["C"]["A"] == 1.0


def test_non_note_relational_endpoints_add_no_entailed_edge():
    """A relational edge whose src/dst id was never registered via upsert_node (absent from
    store.all_nodes()) must not spawn any NEW entailed edge -- the id-membership guard, not
    just IRI shape, decides real-note-ness. reasoning adds nothing here, so the reasoned
    adjacency equals the raw graph-arm adjacency untouched."""
    s = TripleStore()
    s.upsert_node({"id": "A", "type": "Project", "name": "Project A"})
    # "ghost"/"ghost2" are never upserted as nodes -- store.all_nodes() never includes them.
    s.upsert_edge({"src": "A", "predicate": "mentions", "dst": "ghost"})
    s.upsert_edge({"src": "ghost2", "predicate": "mentions", "dst": "A"})

    reasoned = reasoned_adjacency(s)

    # Reasoning entails no new note<->note edge (both dangling endpoints fail the note-id
    # guard), so A3 == A2 exactly -- no spurious edge invented for a non-note endpoint.
    assert reasoned == s.adjacency()


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


def test_type_cohort_ignores_universal_owl_thing_type():
    """type_cohort must group only by the kl: entity classes, NOT by owlrl's universal
    types (owl:Thing / rdfs:Resource) that every materialized note gets. Two notes of
    DIFFERENT kl: entity types share only those universals, so even with type_cohort=True
    they must stay unconnected -- otherwise the toggle would link every note to every
    other note via the owl:Thing cohort and be meaningless."""
    s = TripleStore()
    s.upsert_node({"id": "P1", "type": "Project", "name": "Project One"})
    s.upsert_node({"id": "N1", "type": "Note", "name": "Note One"})

    on = reasoned_adjacency(s, type_cohort=True)

    assert "N1" not in on.get("P1", {})
    assert "P1" not in on.get("N1", {})


def test_type_cohort_excludes_entailed_type_on_non_note():
    """A range axiom (kl:authored_by rdfs:range kl:Person) can entail a kl:Person type on an
    endpoint that was never registered as a note (a dangling authored_by target). type_cohort
    must group only REAL notes: that phantom-typed non-note is never pulled into a cohort, so
    it never gets a cohort edge to a real same-typed note."""
    s = TripleStore()
    s.upsert_node({"id": "P1", "type": "Person", "name": "Person One"})
    s.upsert_node({"id": "P2", "type": "Person", "name": "Person Two"})
    # 'ghost' is never upserted; owlrl entails `ghost a kl:Person` via authored_by's range.
    s.upsert_edge({"src": "P1", "predicate": "authored_by", "dst": "ghost"})

    on = reasoned_adjacency(s, type_cohort=True)

    assert "P2" in on["P1"]  # real kl:Person cohort edge between the two registered Persons
    # the phantom-typed non-note is never cohorted to a real note.
    assert "P2" not in on.get("ghost", {})
    assert "ghost" not in on.get("P2", {})


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
