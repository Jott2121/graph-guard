# graph-guard

A typed knowledge graph behind a RAG retriever so multi-hop questions (answers spread across several documents) can be answered via graph connections instead of pure similarity, plus a measured account of when the heavier RDF/OWL/SHACL/SPARQL semantic stack is actually worth its cost.

- **Status:** active, public repo with CI, 137 tests / 97% coverage
- **Entry points:** `graph_guard/` (the package), `examples/run_sample.py` (no API key needed), `eval/`, `docs/`
- **Run/test:** `pip install -e . && python examples/run_sample.py`
- **KG cache staleness:** the KG stores a `corpus_fingerprint` in its `meta` table and rebuilds when it moves. Do **not** reintroduce an `edges == 0` freshness test — one stale edge blocked rebuild permanently, and because `GraphRetriever` falls back to lexical when a query links to no anchor, a 2-node graph served plausible results silently. Call `service.graph_health(retriever)` before attributing any result to "the graph".
- **Constraints:** measured on a real 517-note vault (+14% hit@10, +26% MRR on multi-hop, zero regression on simple lookups); the reasoned/ontology layer ties the plain graph on retrieval — it earns its keep on fidelity/validation/standards interop, not retrieval lift
