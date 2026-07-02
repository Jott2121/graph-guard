"""Graph-aware retriever: entity-link the query, run Personalized PageRank over the typed
KG, and reciprocal-rank-fuse the graph ranking with the lexical TF-IDF hits — behind
rag-guard's retrieve(query,k)->[{id,text,score}] seam so the pipeline + guards are untouched.

Hybrid by design: if the query links to NO graph anchor, return pure lexical (graphs lose on
simple lookups — GraphRAG-Bench). The graph earns its keep on multi-hop/relational queries.
Injectable (tfidf_fn, text_for) for deterministic tests; the service factory wires real ones.

tfidf_fn and the graph both operate in NOTE-id space (the factory maps chunk hits -> note hits)."""
from __future__ import annotations

import os

from rag_guard.retriever import _toks

from graph_guard.ppr import node_specificity, personalized_pagerank

_RRF_K = 60

_PREFIXES = ("project_", "reference_", "feedback_", "user_")


def _clean_label(node):
    name = node.get("name") or node["id"]
    base = os.path.basename(name).rsplit(".", 1)[0].lower()
    for p in _PREFIXES:
        if base.startswith(p):
            base = base[len(p):]
            break
    return base.replace("_", " ").replace("-", " ")


def link_entities(query, store, *, limit=8):
    """Link query content-words to graph nodes by clean-label-token overlap; best overlap
    first. Links on the node's clean label only (basename minus known prefix minus
    extension) — never on the full id/path, so path segments and project_/reference_-style
    prefixes can't spuriously match every query."""
    q = set(_toks(query))
    if not q:
        return []
    scored = []
    for node in store.all_nodes():
        name_toks = set(_toks(_clean_label(node)))
        overlap = len(q & name_toks)
        if overlap:
            scored.append((overlap, node["id"]))
    scored.sort(reverse=True)
    return [nid for _, nid in scored[:limit]]


def _rrf(ranked_ids):
    return {nid: 1.0 / (_RRF_K + i) for i, nid in enumerate(ranked_ids)}


class GraphRetriever:
    def __init__(self, store, *, tfidf_fn, text_for, k_lexical=10):
        self._store = store
        self._tfidf = tfidf_fn          # (query, k) -> [{id,text,score}] in NOTE-id space
        self._text_for = text_for       # note_id -> str|None
        self._k_lexical = k_lexical

    def retrieve(self, query, k=5):
        lexical = self._tfidf(query, self._k_lexical) or []
        seeds = link_entities(query, self._store)
        if not seeds:
            return lexical[:k]          # hybrid: no anchor -> pure lexical

        adj = self._store.adjacency()
        pr = personalized_pagerank(adj, seeds)
        spec = node_specificity(adj)
        note_scores = {}
        for node in self._store.all_nodes():
            if node.get("note_path"):
                nid = node["id"]
                s = pr.get(nid, 0.0) * spec.get(nid, 1.0)
                if s > 0:
                    note_scores[nid] = s
        graph_ranked = sorted(note_scores, key=note_scores.get, reverse=True)

        lex_ids = [h["id"] for h in lexical]
        lex_rrf, graph_rrf = _rrf(lex_ids), _rrf(graph_ranked)
        fused = {}
        for nid in set(lex_ids) | set(graph_ranked):
            fused[nid] = lex_rrf.get(nid, 0.0) + graph_rrf.get(nid, 0.0)
        ranked = sorted(fused, key=fused.get, reverse=True)[:k]

        lex_text = {h["id"]: h["text"] for h in lexical}
        results = []
        for nid in ranked:
            text = lex_text.get(nid) or self._text_for(nid) or ""
            results.append({"id": nid, "text": text, "score": round(fused[nid], 6)})
        return results
