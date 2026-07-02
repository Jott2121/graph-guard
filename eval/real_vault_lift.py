"""Gate D — the 3-arm retrieval-lift harness (flat TF-IDF vs. graph vs. owlrl-reasoned).

Wires Gate D Tasks 1-4 (reasoned_adjacency, the injectable GraphRetriever adjacency_fn,
eval_probes, eval_metrics) into a single `run()` that builds the KG + retrievers ONCE, runs
every structure-derived probe over all three arms, and reports aggregate hit@k/MRR + lift.

TWO modes:
  - Manual real-vault run (`python -m eval.real_vault_lift`, or `run()` with no args): reads
    Jeff's PRIVATE vault via `rag_guard.config.default_roots()`.
  - CI tests (`tests/test_real_vault_lift.py`): call the SAME `run()` over a small synthetic
    temp-dir vault -- never the private vault.

The vault is private but this repo is public, so the CONTRACT is: `run()`'s returned dict
(and the `eval/results.json` it writes) is AGGREGATE-ONLY -- counts and metric numbers, never
a note id, file path, filename, or query/gold string. `tests/test_real_vault_lift.py` has a
hard leak-check test enforcing this.
"""
from __future__ import annotations

import json
import os

from rag_guard import config
from rag_guard.retriever import Retriever

from graph_guard.eval_metrics import evaluate, lift
from graph_guard.eval_probes import multi_hop_probes, simple_lookup_probes
from graph_guard.extract import _walk_md, build_graph
from graph_guard.graph_retriever import GraphRetriever
from graph_guard.reasoned_graph import reasoned_adjacency
from graph_guard.store import TripleStore

_RESULTS_PATH = os.path.join("eval", "results.json")


def run(roots=None, *, k: int = 10, max_multihop: int | None = None,
        max_simple: int | None = None) -> dict:
    """Build the KG + all three arms ONCE, evaluate every probe over each, and return (and
    write to `eval/results.json`) an aggregate-only comparison. `roots=None` reads Jeff's
    private vault (`rag_guard.config.default_roots()`); tests always pass an explicit
    synthetic `roots`."""
    roots = roots or config.default_roots()

    # --- shared pieces, built ONCE ---
    store = TripleStore(":memory:")
    build_graph(roots, store)
    paths = list(_walk_md(roots))
    docs, text_map = [], {}
    for path in paths:
        try:
            text = open(path, encoding="utf-8", errors="ignore").read()
        except OSError:  # pragma: no cover -- defensive; mirrors service.build_retriever
            continue
        docs.append({"id": path, "text": text})
        text_map[path] = text
    tfidf = Retriever(docs)

    # --- the three arms, as (query, k) -> hits callables ---
    def flat(query, kk):
        return tfidf.retrieve(query, kk)

    graph_retriever = GraphRetriever(store, tfidf_fn=flat, text_for=text_map.get)
    # Build the reasoned adjacency ONCE (owlrl materialization is not cheap) and close over
    # it, rather than handing GraphRetriever a fresh `reasoned_adjacency(store)` call that
    # would re-run owlrl on every single probe.
    radj = reasoned_adjacency(store)
    reasoned_retriever = GraphRetriever(store, tfidf_fn=flat, text_for=text_map.get,
                                         adjacency_fn=lambda: radj)

    # --- probes, generated ONCE ---
    multi_hop, discarded = multi_hop_probes(store)
    simple_lookup = simple_lookup_probes(store)
    capped = False
    if max_multihop is not None and len(multi_hop) > max_multihop:
        multi_hop = multi_hop[:max_multihop]
        capped = True
    if max_simple is not None and len(simple_lookup) > max_simple:
        simple_lookup = simple_lookup[:max_simple]
        capped = True
    probes = multi_hop + simple_lookup

    # --- evaluate each arm over the same probe set ---
    flat_metrics = evaluate(flat, probes, k=k)
    graph_metrics = evaluate(graph_retriever.retrieve, probes, k=k)
    reasoned_metrics = evaluate(reasoned_retriever.retrieve, probes, k=k)

    vault_counts = store.counts()
    note_count = sum(1 for node in store.all_nodes() if node.get("note_path"))

    result = {
        "vault": {
            "nodes": vault_counts["nodes"],
            "edges": vault_counts["edges"],
            "notes": note_count,
        },
        "probes": {
            "multi_hop": len(multi_hop),
            "simple_lookup": len(simple_lookup),
            "discarded": discarded,
            "capped": capped,
        },
        "k": k,
        "arms": {"flat": flat_metrics, "graph": graph_metrics, "reasoned": reasoned_metrics},
        "lift": {
            "graph_vs_flat": lift(graph_metrics, flat_metrics),
            "reasoned_vs_flat": lift(reasoned_metrics, flat_metrics),
            "reasoned_vs_graph": lift(reasoned_metrics, graph_metrics),
        },
    }

    os.makedirs(os.path.dirname(_RESULTS_PATH), exist_ok=True)
    with open(_RESULTS_PATH, "w") as f:
        json.dump(result, f, indent=2)

    _print_table(result)
    return result


def _fmt(value):
    return "  n/a" if value is None else f"{value:.4f}"


def _print_table(result: dict) -> None:
    """Aggregate-only comparison table -- no ids/paths/text, matching the result dict."""
    v, p = result["vault"], result["probes"]
    print(f"vault: {v['notes']} notes, {v['nodes']} nodes, {v['edges']} edges")
    print(f"probes: {p['multi_hop']} multi-hop, {p['simple_lookup']} simple-lookup "
          f"(discarded={p['discarded']}, capped={p['capped']}) @ k={result['k']}")
    header = f"{'arm':<10}{'family':<15}{'hit@1':>8}{'hit@5':>8}{'hit@10':>8}{'mrr':>8}{'n':>6}"
    print(header)
    print("-" * len(header))
    for arm_name, arm in result["arms"].items():
        for family, group in arm.items():
            print(f"{arm_name:<10}{family:<15}{_fmt(group['hit@1']):>8}{_fmt(group['hit@5']):>8}"
                  f"{_fmt(group['hit@10']):>8}{_fmt(group['mrr']):>8}{group['n']:>6}")


if __name__ == "__main__":  # pragma: no cover -- manual real-vault entry point
    run()
    print("\n(results.json is aggregate-only: counts and metrics, no note ids, paths, "
          "filenames, or query/gold text)")
