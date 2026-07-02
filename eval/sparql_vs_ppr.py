"""Architect demo: answer "what did X supersede, transitively?" TWO ways over the SAME small
fixture, and print both results side by side.

  (a) SPARQL property-path over the RDF export (Tier B, graph_guard/fuseki.py) -- exact,
      deterministic closure; the property path literally IS the proof.
  (b) Personalized PageRank over the live SQLite graph (Tier A, graph_guard/graph_retriever.py)
      -- a ranked relevance list that also surfaces related-but-not-superseding nodes.

Companion to docs/SPARQL-vs-PPR.md: the "Side-by-side result" section in that doc is this
script's actual stdout, run once and pasted unedited -- see that doc for the interpretation.
Mirrors eval/eval_multihop.py's shape: a controlled TripleStore fixture, a run() that returns
a comparable dict, __main__ pretty-prints it. `python -m eval.sparql_vs_ppr` to reproduce.
"""
from __future__ import annotations

import json
import time

from graph_guard.fuseki import PREFIXES, supersedes_chain
from graph_guard.graph_retriever import GraphRetriever, link_entities
from graph_guard.rdf_export import node_iri, store_to_graph
from graph_guard.reasoning import materialize
from graph_guard.store import TripleStore

START = "project_v3.md"
QUERY = "what did project v3 supersede"

# The exact-closure answer a correct implementation must return: v3 supersedes v2 supersedes v1.
KNOWN_SUPERSEDED = {"project_v2.md", "project_v1.md"}


def _demo_store() -> TripleStore:
    """v3 -> v2 -> v1 via `supersedes` (the exact chain a correct answer must return) PLUS two
    "noise" nodes reachable only by OTHER predicates (`mentions`, `related`) so PageRank has
    somewhere to diffuse that is NOT the supersedes closure, and a fully disconnected control
    node that should surface in NEITHER result."""
    s = TripleStore()
    s.upsert_node({"id": "project_v1.md", "type": "Project", "name": "Apex Protocol V1",
                   "note_path": "project_v1.md"})
    s.upsert_node({"id": "project_v2.md", "type": "Project", "name": "Apex Protocol V2",
                   "note_path": "project_v2.md"})
    s.upsert_node({"id": "project_v3.md", "type": "Project", "name": "Apex Protocol V3",
                   "note_path": "project_v3.md"})
    s.upsert_node({"id": "reference_apex_spec.md", "type": "Reference", "name": "Apex Spec Reference",
                   "note_path": "reference_apex_spec.md"})
    s.upsert_node({"id": "feedback_apex_review.md", "type": "Feedback", "name": "Apex Review Feedback",
                   "note_path": "feedback_apex_review.md"})
    s.upsert_node({"id": "project_unrelated.md", "type": "Project", "name": "Unrelated Moonshot",
                   "note_path": "project_unrelated.md"})

    s.upsert_edge({"src": "project_v3.md", "predicate": "supersedes", "dst": "project_v2.md"})
    s.upsert_edge({"src": "project_v2.md", "predicate": "supersedes", "dst": "project_v1.md"})
    s.upsert_edge({"src": "project_v3.md", "predicate": "mentions", "dst": "reference_apex_spec.md"})
    s.upsert_edge({"src": "project_v2.md", "predicate": "related", "dst": "feedback_apex_review.md"})
    s.upsert_edge({"src": "reference_apex_spec.md", "predicate": "mentions", "dst": "feedback_apex_review.md"})
    return s


def _entailed_supersedes_transitively(reasoned_graph, start_id: str, candidate_ids) -> list[str]:
    """ASK, per candidate, whether owlrl materialized `kl:supersedesTransitively(start, candidate)`.

    A second, independent SPARQL route to the same closure: instead of a `+` property path over
    the asserted single-hop `kl:supersedes` edges, this queries the reasoner's own materialized
    multi-hop predicate directly (no `+` needed -- the reasoner already did the multi-hop work).
    Real semantic-web systems use this ASK-per-candidate pattern to validate a candidate list
    against a reasoned graph (e.g. a SHACL-style closed-world check)."""
    entailed = []
    for cid in candidate_ids:
        query = PREFIXES + f"""
ASK {{ <{node_iri(start_id)}> kl:supersedesTransitively <{node_iri(cid)}> . }}
"""
        if reasoned_graph.query(query).askAnswer:
            entailed.append(cid)
    return entailed


def _sparql_side(store: TripleStore) -> dict:
    graph = store_to_graph(store)
    candidate_ids = sorted(n["id"] for n in store.all_nodes() if n["id"] != START)

    t0 = time.perf_counter()
    property_path_closure = supersedes_chain(graph, START)
    property_path_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    reasoned = materialize(graph)
    materialize_ms = (time.perf_counter() - t0) * 1000

    entailed = _entailed_supersedes_transitively(reasoned, START, candidate_ids)
    property_path_on_reasoned = supersedes_chain(reasoned, START)

    return {
        "property_path_closure": sorted(property_path_closure),
        "property_path_ms": round(property_path_ms, 4),
        "materialize_ms": round(materialize_ms, 4),
        "entailed_supersedes_transitively": sorted(entailed),
        "property_path_on_reasoned_graph": sorted(property_path_on_reasoned),
    }


def _pagerank_side(store: TripleStore) -> dict:
    def tfidf(_query, _k):
        return []  # isolate the graph leg: no lexical hits to fuse in this fixture

    text_for = {n["id"]: n["name"] for n in store.all_nodes()}.get
    retriever = GraphRetriever(store, tfidf_fn=tfidf, text_for=text_for)

    seeds = link_entities(QUERY, store)

    t0 = time.perf_counter()
    ranked = retriever.retrieve(QUERY, k=len(store.all_nodes()))
    retrieve_ms = (time.perf_counter() - t0) * 1000

    return {
        "seeds": seeds,
        "ranked": ranked,
        "ranked_ids": [hit["id"] for hit in ranked],
        "retrieve_ms": round(retrieve_ms, 4),
    }


def run() -> dict:
    """Build the fixture once and run both engines against it. Returns a plain dict (JSON-safe)
    so it's easy to assert on in tests and to pretty-print from __main__."""
    store = _demo_store()
    return {
        "query": QUERY,
        "start": START,
        "known_superseded": sorted(KNOWN_SUPERSEDED),
        "sparql": _sparql_side(store),
        "pagerank": _pagerank_side(store),
    }


def _print_comparison(result: dict) -> None:
    sparql = result["sparql"]
    pagerank = result["pagerank"]

    print(f'Question: "{result["query"]}"  (start node: {result["start"]})')
    print()
    print("=== SPARQL / OWL (Tier B) -- exact closure ===")
    print(f'  property path (kl:supersedes+, no reasoner) : {sparql["property_path_closure"]}'
          f'   [{sparql["property_path_ms"]} ms]')
    print(f'  owlrl materialize() (OWL 2 RL entailment)    : {sparql["materialize_ms"]} ms')
    print(f'  entailed kl:supersedesTransitively candidates: {sparql["entailed_supersedes_transitively"]}')
    print(f'  property path re-run on reasoned graph       : {sparql["property_path_on_reasoned_graph"]}')
    print()
    print("=== Personalized PageRank (Tier A) -- ranked relevance list ===")
    print(f'  entity-linked seeds: {pagerank["seeds"]}   [{pagerank["retrieve_ms"]} ms]')
    for hit in pagerank["ranked"]:
        flag = "KNOWN SUPERSEDED" if hit["id"] in KNOWN_SUPERSEDED else (
            "start node" if hit["id"] == result["start"] else "noise (not superseded)"
        )
        print(f'    {hit["score"]:.6f}  {hit["id"]:<28} {flag}')
    print()
    noise_ranked_above_known = [
        hit["id"] for hit in pagerank["ranked"]
        if hit["id"] not in KNOWN_SUPERSEDED and hit["id"] != result["start"]
    ]
    print("=== Interpretation ===")
    print(f'  SPARQL returns EXACTLY the known superseded set: {result["known_superseded"]}.')
    if noise_ranked_above_known:
        print(f'  PageRank also surfaces non-superseding nodes in its ranked list: {noise_ranked_above_known}'
              " -- fuzzy relevance, not a formal answer.")
    else:
        print("  PageRank's ranked list happened to contain no noise nodes above the known set in this run.")


if __name__ == "__main__":
    result = run()
    _print_comparison(result)
    print()
    print("=== raw run() dict (JSON) ===")
    print(json.dumps(result, indent=2))
