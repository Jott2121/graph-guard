"""The cached KG must rebuild when the corpus changes, and must never fail silently.

Regression for a defect that invalidated a full day of retrieval measurements. The cached
KG held 2 nodes and 1 edge while the corpus had ~590 notes, because build_retriever
rebuilt only when `edges == 0` -- one stale edge blocked the rebuild permanently. Worse,
GraphRetriever falls back to pure lexical whenever a query links to no anchor, which is a
deliberate hybrid behaviour, so an empty graph produces plausible results and reports
nothing wrong. Every arm labelled "graph" was in fact lexical.

The lesson those tests encode: a component that degrades silently on a stale cache will be
measured as working.
"""
import pytest

from graph_guard import service
from graph_guard.store import TripleStore


@pytest.fixture
def vault(tmp_path):
    v = tmp_path / "vault"
    v.mkdir()
    (v / "alpha.md").write_text("Alpha note about elk. Links to [[beta]].")
    (v / "beta.md").write_text("Beta note about archery. Links to [[gamma]].")
    (v / "gamma.md").write_text("Gamma note about september.")
    return v


def _counts(path):
    return TripleStore(path).counts()


def test_builds_a_real_graph_from_a_vault(vault, tmp_path):
    kg = str(tmp_path / "kg.sqlite")
    service.build_retriever([str(vault)], kg_path=kg)
    assert _counts(kg)["edges"] >= 2


def test_unchanged_corpus_reuses_the_cache(vault, tmp_path):
    kg = str(tmp_path / "kg.sqlite")
    service.build_retriever([str(vault)], kg_path=kg)
    before = _counts(kg)
    service.build_retriever([str(vault)], kg_path=kg)
    assert _counts(kg) == before


def test_changed_corpus_rebuilds_the_cache(vault, tmp_path):
    """The actual bug: a non-empty stale KG was treated as current forever."""
    kg = str(tmp_path / "kg.sqlite")
    service.build_retriever([str(vault)], kg_path=kg)
    (vault / "delta.md").write_text("Delta note. Links to [[alpha]] and [[beta]].")
    service.build_retriever([str(vault)], kg_path=kg)
    ids = {n["id"] for n in TripleStore(kg).all_nodes()}
    assert any("delta" in i.lower() for i in ids), "new note never entered the graph"


def test_a_stale_kg_with_one_edge_does_not_block_rebuild(vault, tmp_path):
    """Exactly the shape of the real failure: 2 nodes, 1 edge, non-zero, never rebuilt."""
    kg = str(tmp_path / "kg.sqlite")
    store = TripleStore(kg)
    store.upsert_node({"id": "stale-a", "type": "Note", "name": "stale a"})
    store.upsert_node({"id": "stale-b", "type": "Note", "name": "stale b"})
    store.upsert_edge({"src": "stale-a", "predicate": "mentions", "dst": "stale-b"})
    assert _counts(kg)["edges"] == 1

    service.build_retriever([str(vault)], kg_path=kg)
    ids = {n["id"] for n in TripleStore(kg).all_nodes()}
    assert any("alpha" in i.lower() for i in ids), "stale KG was served instead of rebuilt"


def test_explicit_rebuild_still_forces_a_rebuild(vault, tmp_path):
    kg = str(tmp_path / "kg.sqlite")
    service.build_retriever([str(vault)], kg_path=kg)
    service.build_retriever([str(vault)], kg_path=kg, rebuild=True)
    assert _counts(kg)["edges"] >= 2


def test_graph_health_reports_an_empty_graph(vault, tmp_path):
    """A caller measuring 'the graph' must be able to ask whether one is actually loaded,
    instead of silently benchmarking the lexical fallback."""
    kg = str(tmp_path / "kg.sqlite")
    retriever = service.build_retriever([str(vault)], kg_path=kg)
    health = service.graph_health(retriever)
    assert health["nodes"] >= 3 and health["edges"] >= 2
    assert health["empty"] is False


def test_graph_health_flags_a_degenerate_graph(tmp_path):
    empty_vault = tmp_path / "v"
    empty_vault.mkdir()
    (empty_vault / "solo.md").write_text("A note with no links at all.")
    kg = str(tmp_path / "kg.sqlite")
    retriever = service.build_retriever([str(empty_vault)], kg_path=kg)
    health = service.graph_health(retriever)
    assert health["edges"] == 0
    assert health["empty"] is True, "no edges means the graph arm is lexical-only"
