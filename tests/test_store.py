from graph_guard.store import TripleStore

def test_upsert_and_get_node():
    s = TripleStore()
    s.upsert_node({"id": "Gina", "type": "Person", "name": "Gina"})
    n = s.node("Gina")
    assert n["type"] == "Person" and n["name"] == "Gina" and n["attrs"] == {}

def test_upsert_node_replaces():
    s = TripleStore()
    s.upsert_node({"id": "x", "type": "Note", "name": "x"})
    s.upsert_node({"id": "x", "type": "Project", "name": "x"})
    assert s.node("x")["type"] == "Project"
    assert s.counts()["nodes"] == 1

def test_edges_and_neighbors():
    s = TripleStore()
    s.upsert_edge({"src": "A", "predicate": "supersedes", "dst": "B",
                   "confidence": 0.9, "extractor": "frontmatter"})
    out = s.neighbors("A", "out")
    assert len(out) == 1 and out[0]["dst"] == "B" and out[0]["predicate"] == "supersedes"
    assert s.neighbors("B", "in")[0]["src"] == "A"

def test_adjacency_symmetric_weighted():
    s = TripleStore()
    s.upsert_edge({"src": "A", "predicate": "mentions", "dst": "B", "confidence": 1.0})
    adj = s.adjacency()
    assert adj["A"]["B"] == 1.0 and adj["B"]["A"] == 1.0

def test_missing_node_is_none():
    assert TripleStore().node("nope") is None

def test_persist_to_disk(tmp_path):
    p = str(tmp_path / "kg.sqlite")
    s = TripleStore(p); s.upsert_node({"id": "A", "type": "Note", "name": "A"}); s.close()
    s2 = TripleStore(p)
    assert s2.node("A") is not None
