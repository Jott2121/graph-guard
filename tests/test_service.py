from graph_guard import service

def _vault(tmp_path):
    (tmp_path / "leo.md").write_text("the leo bus project")
    (tmp_path / "bow.md").write_text("## Supersedes\nbow replaces [[leo]]")
    return [str(tmp_path)]

def test_build_retriever_and_query(tmp_path):
    roots = _vault(tmp_path)
    service.reset()
    gr = service.build_retriever(roots, kg_path=":memory:")
    hits = gr.retrieve("leo bus", k=5)
    assert hits and all(set(h) == {"id", "text", "score"} for h in hits)

def test_query_uses_singleton(tmp_path, monkeypatch):
    roots = _vault(tmp_path)
    service.reset()
    monkeypatch.setattr("rag_guard.config.default_roots", lambda: roots)
    monkeypatch.setattr("graph_guard.service.kg_cache_path", lambda: ":memory:")
    hits = service.query("leo", k=3)
    assert isinstance(hits, list) and service._SINGLETON is not None

def test_build_cli_reports_counts(tmp_path, monkeypatch):
    roots = _vault(tmp_path)
    from graph_guard import build_cli
    monkeypatch.setattr("graph_guard.service.kg_cache_path", lambda: str(tmp_path / "kg.sqlite"))
    counts = build_cli.main(roots)
    assert counts["notes"] == 2 and counts["edges"] >= 1 and counts["nodes"] >= 2

def test_build_retriever_reuses_populated_kg(tmp_path):
    roots = _vault(tmp_path)
    kg = str(tmp_path / "kg.sqlite")
    service.build_retriever(roots, kg_path=kg)          # first build populates the sqlite
    r2 = service.build_retriever(roots, kg_path=kg)      # second call must reuse it
    assert r2._store.counts()["edges"] > 0

def test_answer_refuses_when_no_graph_anchor(tmp_path, monkeypatch):
    roots = _vault(tmp_path); service.reset()
    from rag_guard.providers import FakeProvider
    monkeypatch.setattr("rag_guard.config.default_roots", lambda: roots)
    monkeypatch.setattr("graph_guard.service.kg_cache_path", lambda: ":memory:")
    out = service.answer("zzz unrelated gibberish", FakeProvider("x"), k=3)
    assert out["refused"] is True and out["sources"] == []

def test_answer_grounds_when_anchored(tmp_path, monkeypatch):
    roots = _vault(tmp_path); service.reset()
    from rag_guard.providers import FakeProvider
    monkeypatch.setattr("rag_guard.config.default_roots", lambda: roots)
    monkeypatch.setattr("graph_guard.service.kg_cache_path", lambda: ":memory:")
    out = service.answer("leo bus", FakeProvider("the leo bus project"), k=3)
    assert out["refused"] is False and "answer" in out and isinstance(out["sources"], list)
