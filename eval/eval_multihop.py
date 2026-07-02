"""Controlled multi-hop eval: prove the GraphRetriever surfaces a note that flat TF-IDF
misses because it shares NO query words but sits one typed hop (supersedes) from a lexical
match. This is the canonical case where graph retrieval beats flat lexical (GraphRAG-Bench:
graphs win on multi-hop, not simple lookups)."""
from __future__ import annotations

from graph_guard.graph_retriever import GraphRetriever
from graph_guard.store import TripleStore


def _multihop_store():
    s = TripleStore()
    s.upsert_node({"id": "ledger.md", "type": "Project", "name": "trade ledger", "note_path": "ledger.md"})
    s.upsert_node({"id": "apex.md", "type": "Project", "name": "apex protocol", "note_path": "apex.md"})
    # apex replaced the ledger; apex shares no words with the query below
    s.upsert_edge({"src": "apex.md", "predicate": "supersedes", "dst": "ledger.md", "confidence": 1.0})
    return s


def run():
    s = _multihop_store()
    query = "what replaced the trade ledger"

    # flat lexical only knows 'ledger' (the query mentions it); 'apex' shares no query words
    def tfidf(q, k):
        return [{"id": "ledger.md", "text": "the trade ledger", "score": 0.8}]

    text_for = {"apex.md": "apex protocol", "ledger.md": "the trade ledger"}.get
    gr = GraphRetriever(s, tfidf_fn=tfidf, text_for=text_for)

    flat_ids = [h["id"] for h in tfidf(query, 5)]
    graph_ids = [h["id"] for h in gr.retrieve(query, k=5)]
    return {
        "query": query,
        "flat": flat_ids,
        "graph": graph_ids,
        "flat_found_apex": "apex.md" in flat_ids,
        "graph_found_apex": "apex.md" in graph_ids,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(run(), indent=2))
