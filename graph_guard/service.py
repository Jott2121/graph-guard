"""Warm singleton over the vault: build the KG + a note-level TF-IDF leg (both in full-note-
path id space so they fuse cleanly), and expose graph-aware query(). rag-guard's Retriever is
the lexical leg; graph_retriever fuses PPR over the KG."""
from __future__ import annotations

import hashlib
import os

from rag_guard import config
from rag_guard.pipeline import REFUSAL, build_grounded_prompt
from rag_guard.retriever import Retriever

from graph_guard.extract import _walk_md, build_graph
from graph_guard.graph_retriever import GraphRetriever, link_entities
from graph_guard.guards import graph_groundedness, should_refuse_structural
from graph_guard.store import TripleStore

_SINGLETON = None


def kg_cache_path():
    base = os.path.expanduser("~/.cache/graph-guard")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "kg.sqlite")


def reset():
    global _SINGLETON
    _SINGLETON = None


KG_FINGERPRINT_KEY = "corpus_fingerprint"


def corpus_fingerprint(roots) -> str:
    """Hash of the corpus's markdown paths, mtimes and sizes.

    The KG has to know which corpus it was built from. The previous test -- rebuild only
    when `edges == 0` -- meant a single stale edge blocked the rebuild permanently, and
    because GraphRetriever falls back to lexical whenever a query links to no anchor, the
    result was a 2-node graph serving plausible lexical results and reporting nothing
    wrong. Silent degradation on a stale cache gets measured as working.
    """
    h = hashlib.sha256()
    for path in sorted(_walk_md(roots)):
        try:
            st = os.stat(path)
        except OSError:
            continue
        h.update(f"{path}:{int(st.st_mtime)}:{st.st_size};".encode())
    return h.hexdigest()


def graph_health(retriever) -> dict:
    """Is a graph actually loaded? Ask before attributing anything to 'the graph'.

    `empty` means the graph arm cannot contribute: with no edges there is nothing for
    PageRank to traverse, so every query is served by the lexical leg alone."""
    counts = retriever._store.counts()
    return {**counts, "empty": counts["edges"] == 0}


def build_retriever(roots=None, *, kg_path=None, llm_fn=None, rebuild=False):
    roots = roots or config.default_roots()
    store = TripleStore(kg_path or ":memory:")
    current = corpus_fingerprint(roots)
    if rebuild or store.get_meta(KG_FINGERPRINT_KEY) != current:
        # Clear first: build_graph upserts, so without this a rename or deletion leaves
        # orphaned nodes from the previous corpus in place forever.
        store.clear()
        build_graph(roots, store, llm_fn=llm_fn)
        store.set_meta(KG_FINGERPRINT_KEY, current)
    docs, text_map = [], {}
    for path in _walk_md(roots):
        try:
            t = open(path, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        docs.append({"id": path, "text": t})
        text_map[path] = t
    tfidf = Retriever(docs) if docs else None
    tfidf_fn = (lambda q, k: tfidf.retrieve(q, k)) if tfidf else (lambda q, k: [])
    return GraphRetriever(store, tfidf_fn=tfidf_fn, text_for=text_map.get)


def _get_retriever(roots=None):
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = build_retriever(roots, kg_path=kg_cache_path())
    return _SINGLETON


def answer(query_text, provider, k=5, *, roots=None):
    """Graph-guarded answer: refuse when the query links to no graph node (structural gate),
    else retrieve, generate via provider, and score entity-overlap grounding against the
    retrieved subgraph. provider is any object with .complete(prompt)->str."""
    retr = _get_retriever(roots)
    seeds = link_entities(query_text, retr._store)
    if should_refuse_structural(query_text, seeds):
        return {"answer": REFUSAL, "refused": True, "grounded": None, "support": 0.0, "sources": []}
    hits = retr.retrieve(query_text, k)
    contexts = [h["text"] for h in hits]
    raw = provider.complete(build_grounded_prompt(query_text, contexts))
    g = graph_groundedness(raw, [h["id"] for h in hits], retr._store)
    return {"answer": raw, "refused": False, "grounded": g["grounded"],
            "support": g["support"], "sources": [h["id"] for h in hits]}


def query(text, k=5, *, roots=None):
    return _get_retriever(roots).retrieve(text, k)
