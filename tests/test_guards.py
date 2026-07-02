from graph_guard.store import TripleStore
from graph_guard.guards import graph_groundedness, should_refuse_structural, contradicts_local

def _store():
    s = TripleStore()
    s.upsert_node({"id": "bow.md", "type": "Project", "name": "bow", "note_path": "bow.md"})
    s.upsert_node({"id": "leo.md", "type": "Project", "name": "leo", "note_path": "leo.md"})
    s.upsert_node({"id": "huntdialed", "type": "Project", "name": "huntdialed", "note_path": "huntdialed.md"})
    s.upsert_edge({"src": "huntdialed", "predicate": "has_status", "dst": "LIVE", "confidence": 1.0})
    return s

def test_groundedness_entity_overlap():
    g = graph_groundedness("bow is the answer", ["bow.md"], _store())
    assert g["grounded"] and g["support"] == 1.0

def test_groundedness_partial():
    g = graph_groundedness("bow and leo", ["bow.md"], _store())  # leo not in subgraph
    assert g["support"] == 0.5

def test_groundedness_no_entities():
    g = graph_groundedness("zzz gibberish", ["bow.md"], _store())
    assert not g["grounded"] and g["support"] == 0.0

def test_structural_refuse():
    assert should_refuse_structural("q", []) is True
    assert should_refuse_structural("q", ["bow.md"]) is False

def test_contradiction_functional():
    s = _store()
    assert contradicts_local([("huntdialed", "has_status", "FROZEN")], s) is True
    assert contradicts_local([("huntdialed", "has_status", "LIVE")], s) is False

def test_no_contradiction_nonfunctional():
    assert contradicts_local([("bow.md", "mentions", "x")], _store()) is False
