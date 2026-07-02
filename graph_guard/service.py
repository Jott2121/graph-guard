"""Warm singleton over the vault: build the KG + a note-level TF-IDF leg (both in full-note-
path id space so they fuse cleanly), and expose graph-aware query(). rag-guard's Retriever is
the lexical leg; graph_retriever fuses PPR over the KG."""
from __future__ import annotations

import os

from rag_guard import config
from rag_guard.retriever import Retriever

from graph_guard.extract import _walk_md, build_graph
from graph_guard.graph_retriever import GraphRetriever
from graph_guard.store import TripleStore

_SINGLETON = None


def kg_cache_path():
    base = os.path.expanduser("~/.cache/graph-guard")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "kg.sqlite")


def reset():
    global _SINGLETON
    _SINGLETON = None


def build_retriever(roots=None, *, kg_path=None, llm_fn=None):
    roots = roots or config.default_roots()
    store = TripleStore(kg_path or ":memory:")
    build_graph(roots, store, llm_fn=llm_fn)
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


def query(text, k=5, *, roots=None):
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = build_retriever(roots, kg_path=kg_cache_path())
    return _SINGLETON.retrieve(text, k)
