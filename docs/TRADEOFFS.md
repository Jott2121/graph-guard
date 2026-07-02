# When does a graph / ontology layer earn its cost?

The architect question isn't "graph or vectors?" — it's "which retrieval substrate for which
query, and how much formal semantics is worth paying for?" This is the judgment graph-guard is
built to exercise, and the honest answer has three parts.

## 1. Graph vs. flat retrieval — route, don't replace

| Query shape | Winner | Why |
|---|---|---|
| Simple fact lookup ("what's my mortgage rate?") | **Flat (TF-IDF/vector)** | The answer is in one chunk; graph traversal adds latency + noise. GraphRAG-Bench shows graphs *underperform* here. |
| Multi-hop / relational ("what superseded X, and why?") | **Graph** | The answer note may share no words with the query; it's reached by traversing typed edges (HippoRAG PPR). |
| Global / thematic ("summarize the state of venture Y") | **Graph (community summaries)** | No single chunk holds the theme; it's aggregated across notes (GraphRAG global search). |
| Disambiguation ("Mercury" the planet vs. element) | **Graph** | Typed entity nodes resolve the sense. |

graph-guard's answer: **hybrid routing** — link the query to graph anchors; if none, return pure
lexical. The graph is a *scalpel for relationships*, not a replacement for search.

## 2. How much ontology formalism — right-size, don't maximize

More OWL is not more better. "Knowledge Conceptualization Impacts RAG Efficacy" (arXiv 2507.09389)
shows an LLM's ability to query a triplestore *degrades* as the schema grows more expressive.
Design implication, and graph-guard's Tier-A choice:

- **Live path:** a small **closed** predicate set + typed nodes. Higher extraction precision,
  reliable to query, cheap to reason over.
- **Formal richness (RDF/OWL/SHACL, reasoners):** valuable for **governance, validation, interop,
  and entailment** — the enterprise semantic-layer use case — but paid for in a **Tier-B export**,
  not forced onto every retrieval.

## 3. Where the heavyweight enterprise stack *is* right

Full RDF/OWL/SPARQL + a graph DB (e.g. AWS Neptune) + an external reasoner (RDFox) earns its cost
when you need: shared meaning across **heterogeneous** enterprise data; **governance/lineage**;
**materialized inference** (derive facts, don't just retrieve them); and **interop** via open
standards. It's overkill for a single 750-note personal vault — which is exactly why graph-guard
runs a pragmatic SQLite/PageRank core for daily use and treats RDF/OWL as a Tier-B fidelity layer.

**The one-liner:** *use the graph where relationships carry the answer, keep the ontology as lean
as the query engine can reliably use, and reserve the full semantic-web stack for enterprise
governance and inference — not for making a personal notes search 200ms slower.*

Sources: GraphRAG (arXiv 2404.16130), HippoRAG (2405.14831), LightRAG (2410.05779), OG-RAG
(2412.15235), GraphRAG-Bench (2506.05690), Knowledge Conceptualization (2507.09389); AWS Neptune +
Bedrock Knowledge Bases GraphRAG; W3C RDF/OWL/SHACL/SPARQL, schema.org, SKOS.
