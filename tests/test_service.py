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
