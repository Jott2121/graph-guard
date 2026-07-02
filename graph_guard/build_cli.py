"""graph-guard-build: (re)build the knowledge graph over the vault; print node/edge counts."""
from __future__ import annotations

import os
import sys

from rag_guard import config

from graph_guard.extract import build_graph
from graph_guard.service import kg_cache_path
from graph_guard.store import TripleStore


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    roots = argv or config.default_roots()
    path = kg_cache_path()
    try:
        os.remove(path)
    except OSError:
        pass
    store = TripleStore(path)
    counts = build_graph(roots, store)
    counts.update(store.counts())
    print(counts)
    return counts


if __name__ == "__main__":
    main()
