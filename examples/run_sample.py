"""Runnable sample: watch a knowledge graph answer a multi-hop question that plain lexical
search cannot — on 7 tiny notes, with no API key and no model (deterministic extraction).

    python examples/run_sample.py

The point: the OWNER of a problem is usually not written next to the problem. Lexical search
only finds text that looks like the query, so it cannot hop from a symptom to the person who
owns it. The graph can, by walking typed relationships between notes.

This prints the two relevance signals the shipped GraphRetriever fuses:
  - GRAPH relevance   = Personalized PageRank from the query's anchor, x node specificity
  - LEXICAL relevance = plain TF-IDF (what vanilla RAG sees)
"""
import os

from rag_guard.retriever import Retriever

from graph_guard import service
from graph_guard.graph_retriever import link_entities
from graph_guard.ppr import node_specificity, personalized_pagerank

HERE = os.path.dirname(os.path.abspath(__file__))
VAULT = os.path.join(HERE, "sample_vault")


def graph_relevance(query, store):
    """Exactly what GraphRetriever uses for its graph leg: anchor the query, run PPR, weight
    by specificity, keep real notes. Returns [(score, note_id)] high first."""
    seeds = link_entities(query, store)
    adj = store.adjacency()
    pr = personalized_pagerank(adj, seeds)
    spec = node_specificity(adj)
    rows = [(pr.get(n["id"], 0.0) * spec.get(n["id"], 1.0), n["id"])
            for n in store.all_nodes() if n.get("note_path")]
    return seeds, sorted(rows, reverse=True)


def lexical_relevance(query, k=7):
    """A plain TF-IDF retriever over the same notes — i.e. what vanilla RAG sees."""
    docs = [{"id": p, "text": open(p, encoding="utf-8").read()} for p in _paths()]
    return [(h["score"], h["id"]) for h in Retriever(docs).retrieve(query, k)]


def _paths():
    return [os.path.join(VAULT, f) for f in sorted(os.listdir(VAULT)) if f.endswith(".md")]


def table(title, rows, notes=None):
    print(title)
    for score, nid in rows:
        tag = f"   <- {notes[os.path.basename(nid)]}" if notes and os.path.basename(nid) in notes else ""
        print(f"  {os.path.basename(nid):22} {score:.6f}{tag}")
    print()


def main():
    service.reset()
    gr = service.build_retriever([VAULT], kg_path=":memory:")
    print(f"built graph over 7 notes: {gr._store.counts()}\n")

    q = "p99 cache eviction latency owner"
    print(f'QUERY (multi-hop): "{q}"\n')

    seeds, grows = graph_relevance(q, gr._store)
    print(f"the query anchors to graph node: {[os.path.basename(s) for s in seeds]}\n")
    table("GRAPH relevance (PPR from the anchor x specificity):", grows, notes={
        "cache-eviction.md": "the anchor (the symptom)",
        "search-revamp.md": "1 hop: the project the bug is part of",
        "vector-index.md":  "also part of that project",
        "maya-chen.md":     "2 hops: she OWNS the project   *** the answer ***",
    })
    table("LEXICAL relevance (plain TF-IDF, what vanilla RAG sees):", lexical_relevance(q))

    print("Maya shares NO words with the query, so lexical scores her 0.00 and can never")
    print("surface her. The graph gives her real relevance by walking the relationships:")
    print("cache-eviction -> search-revamp -> Maya Chen. That is the multi-hop lift, in miniature.")
    print("(The shipped GraphRetriever.retrieve() reciprocal-rank-fuses these two signals, so")
    print(" Maya rides into the retrieved context on the graph leg.)\n")
    print("-" * 78 + "\n")

    q2 = "travel reimbursement per diem"
    print(f'QUERY (simple lookup): "{q2}"\n')
    g_top = gr.retrieve(q2, 1)[0]["id"]
    l_top = lexical_relevance(q2, 1)[0][1]
    print(f"  graph-aware top hit : {os.path.basename(g_top)}")
    print(f"  lexical top hit     : {os.path.basename(l_top)}")
    print("  -> they agree. On a simple lookup the graph adds no anchor path, so it falls back")
    print("     to lexical and does not hurt the easy case.")


if __name__ == "__main__":
    main()
