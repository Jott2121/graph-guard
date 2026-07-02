"""Graph-tightened guards — stronger than lexical token overlap.

- graph_groundedness: fraction of the answer's linkable entities present in the retrieved
  subgraph (entity overlap, not token overlap).
- should_refuse_structural: refuse when the query links to ZERO known graph nodes (fixes the
  out-of-corpus false-accept where lexical TF-IDF spikes on one shared rare word).
- contradicts_local: for FUNCTIONAL predicates, flag when the answer asserts an object that
  conflicts with the one already stored (makes rag-guard's contradicts_local real)."""
from __future__ import annotations

from graph_guard import schema
from graph_guard.graph_retriever import link_entities


def graph_groundedness(answer, subgraph_node_ids, store, *, threshold=0.5):
    ans_entities = link_entities(answer, store, limit=50)
    if not ans_entities:
        return {"grounded": False, "support": 0.0}
    sub = set(subgraph_node_ids)
    hit = sum(1 for e in ans_entities if e in sub)
    support = hit / len(ans_entities)
    return {"grounded": support >= threshold, "support": round(support, 4)}


def should_refuse_structural(query, linked_nodes):
    return not linked_nodes


def contradicts_local(answer_triples, store):
    """answer_triples: iterable of (subject, predicate, object). True if any functional-
    predicate assertion conflicts with an edge already in the store."""
    for (s, p, o) in answer_triples:
        if p not in schema.FUNCTIONAL:
            continue
        for e in store.neighbors(s, "out"):
            if e["predicate"] == p and e["dst"] != o:
                return True
    return False
