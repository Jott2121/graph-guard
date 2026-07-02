from graph_guard.store import TripleStore
from graph_guard.graph_retriever import GraphRetriever, link_entities

def _store():
    s = TripleStore()
    s.upsert_node({"id": "leo.md", "type": "Project", "name": "leo bus", "note_path": "leo.md"})
    s.upsert_node({"id": "bow.md", "type": "Project", "name": "bow chief of staff", "note_path": "bow.md"})
    s.upsert_edge({"src": "bow.md", "predicate": "supersedes", "dst": "leo.md", "confidence": 1.0})
    return s

def test_link_entities_matches_by_name():
    assert "leo.md" in link_entities("what superseded the leo bus", _store())

def test_multihop_pulls_note_tfidf_missed():
    s = _store()
    def tfidf(q, k): return [{"id": "leo.md", "text": "the leo bus", "score": 0.5}]
    def text_for(nid): return {"bow.md": "bow supersedes leo", "leo.md": "the leo bus"}.get(nid)
    gr = GraphRetriever(s, tfidf_fn=tfidf, text_for=text_for)
    ids = [h["id"] for h in gr.retrieve("what superseded the leo bus", k=5)]
    assert "bow.md" in ids  # graph traversal surfaced the note lexical search missed

def test_hybrid_no_seed_returns_lexical():
    s = _store()
    def tfidf(q, k): return [{"id": "x.md", "text": "t", "score": 0.9}]
    gr = GraphRetriever(s, tfidf_fn=tfidf, text_for=lambda n: None)
    out = gr.retrieve("zzz totally unrelated gibberish", k=5)
    assert [h["id"] for h in out] == ["x.md"]

def test_retrieve_shape():
    s = _store()
    gr = GraphRetriever(s, tfidf_fn=lambda q, k: [{"id": "leo.md", "text": "t", "score": 0.5}],
                        text_for=lambda n: "x")
    for h in gr.retrieve("leo", k=3):
        assert set(h) == {"id", "text", "score"}

def test_injected_adjacency_changes_ranking():
    s = _store()
    s.upsert_node({"id": "other.md", "type": "Project", "name": "other project", "note_path": "other.md"})
    def tfidf(q, k): return []  # no lexical hits -> ranking is driven purely by the graph
    def text_for(nid): return {"bow.md": "bow", "leo.md": "leo", "other.md": "other"}.get(nid)
    # custom adjacency connects the seed (leo.md) to other.md instead of bow.md
    custom_adj = {"leo.md": {"other.md": 1.0}, "other.md": {"leo.md": 1.0}}
    gr = GraphRetriever(s, tfidf_fn=tfidf, text_for=text_for, adjacency_fn=lambda: custom_adj)
    ids = [h["id"] for h in gr.retrieve("what superseded the leo bus", k=5)]
    assert "other.md" in ids   # reachable only via the injected adjacency
    assert "bow.md" not in ids  # reachable only via the store's default adjacency, not the injected one

def test_link_entities_ignores_path_and_prefix_tokens():
    from graph_guard.store import TripleStore
    s = TripleStore()
    s.upsert_node({"id": "/home/jeff/Documents/Wiki/project_leo_bus.md", "type": "Project",
                   "name": "project_leo_bus", "note_path": "/home/jeff/Documents/Wiki/project_leo_bus.md"})
    # a query full of PATH/PREFIX words must NOT link the node (those aren't real content)
    assert link_entities("documents wiki project", s) == []
    # a query with the real label DOES link it
    assert "/home/jeff/Documents/Wiki/project_leo_bus.md" in link_entities("leo bus", s)
