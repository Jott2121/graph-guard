# graph-guard

**Ontology/graph-aware retrieval over a personal knowledge vault.** Turns a folder of
markdown (Obsidian `[[wikilinks]]` + YAML frontmatter) into a typed knowledge graph, then
retrieves with multi-hop **Personalized PageRank fused with lexical TF-IDF** — behind
[rag-guard](https://github.com/Jott2121/rag-guard)'s `retrieve()` seam, so its guards and
pipeline are reused unchanged. Tightens grounding with the graph (entity-overlap grounding, a
structural refuse gate, and functional-predicate contradiction detection).

> 🧩 **Tier A (this)** is the pragmatic working core — near-stdlib, fast, tested. **Tier B**
> (next) is a full RDF/OWL/SHACL + SPARQL layer on a local triplestore for enterprise-fidelity
> and interop. The point of shipping both is judgment: knowing *when* the heavyweight semantic
> stack earns its cost — and when it doesn't.

## Why (and the honest tradeoff)

Flat vector/lexical RAG treats a corpus as a bag of chunks — it can't traverse relationships,
disambiguate entities, or answer "what superseded X?" when the answer note shares no words with
the question. A typed knowledge graph can. But graphs are **not** a free win:

- **Graphs beat flat retrieval on multi-hop / relational / thematic queries** — evidence scattered
  across notes, connected by typed edges ([HippoRAG](https://arxiv.org/abs/2405.14831),
  [GraphRAG](https://arxiv.org/abs/2404.16130)).
- **Flat retrieval beats graphs on simple fact lookups** — and over-formalized ontologies can *hurt*
  an LLM's ability to query them ([GraphRAG-Bench](https://arxiv.org/abs/2506.05690),
  [Knowledge Conceptualization Impacts RAG Efficacy](https://arxiv.org/abs/2507.09389)).

So graph-guard is **hybrid by design**: if a query links to no graph anchor, it returns pure
lexical; the graph earns its keep on the queries where relationships matter. The live-path schema
is kept **lean and right-sized** on purpose.

## How it works (Tier A)

```
Obsidian vault (frontmatter + [[wikilinks]] + prose)
   │  extract.py   3-tier: frontmatter + wikilinks (deterministic, free) → LLM (optional, off by default)
   │               wikilinks resolve to real notes; edges typed by frontmatter, heading, and inline cues
   ▼
SQLite triple store (store.py)   nodes + edges, with provenance + confidence
   │  adjacency → Personalized PageRank (ppr.py, stdlib)
   ▼
GraphRetriever.retrieve(query, k)  (graph_retriever.py)
   entity-link query → PPR over typed edges → reciprocal-rank-fuse with TF-IDF → hybrid route
   ▼
rag-guard pipeline + tightened guards (guards.py)
   entity-overlap grounding · zero-node structural refuse · functional-predicate contradiction
```

**Lean closed schema** (`schema.py`): entities `Person/Project/Reference/Feedback/Decision/Claim/
Source/Tool/Event/Concept` (mapped to schema.org + SKOS in Tier B); a closed predicate set
(`mentions, about, is_part_of, authored_by, supersedes, blocks, depends_on, decides, supports,
refutes, has_status, broader/narrower/related`). Functional predicates (`has_status, supersedes`)
power contradiction checks.

## Install / run

```bash
pip install -e ".[dev]"                 # depends on guarded-rag; Tier A core is near-stdlib
PYTHONPATH=. python -m pytest -q        # test suite
PYTHONPATH=. graph-guard-build          # build the KG over your vault (rag-guard's default roots)
```

```python
from graph_guard import service

# retrieval only (hybrid-routed graph + lexical):
hits = service.query("what superseded the leo bus", k=5)

# graph-GUARDED answer (structural refuse + entity-overlap grounding actually run here):
from rag_guard.providers import FakeProvider   # swap for a real provider
out = service.answer("what superseded the leo bus", FakeProvider("..."), k=5)
# {'answer', 'refused', 'grounded', 'support', 'sources'}
```

The guards run in `service.answer()`, not inside `retrieve()` — `retrieve()` is retrieval-only so
it drops cleanly behind rag-guard's seam; `answer()` composes the structural refuse gate +
entity-overlap grounding around a provider.

**Build cost (measured on a real ~750-note vault):** a 686-node / 1,772-edge typed graph built in
~1.4s (deterministic tiers, no model calls). Note the `eval/` case is a *controlled* 2-node
demonstration that the multi-hop **mechanism** works (the graph returns a note flat TF-IDF misses
because it shares no query words but sits one typed hop away) — it proves the mechanism, not a
retrieval-quality lift number on the full vault (unquantified; see limits).

## Where this sits in the landscape (prior art)

None of the ideas are novel — the value is a small, auditable, near-stdlib graph layer over an
existing vault, with honest tradeoff judgment. Lineage:
[GraphRAG](https://arxiv.org/abs/2404.16130) (local/global/community summaries),
[LightRAG](https://arxiv.org/abs/2410.05779) (lightweight dual-level),
[HippoRAG](https://arxiv.org/abs/2405.14831) (Personalized PageRank multi-hop),
[OG-RAG](https://arxiv.org/abs/2412.15235) (ontology-grounded), and the
[Personal Knowledge Graph survey](https://arxiv.org/abs/2304.09572);
schema/taxonomy standards [schema.org](https://schema.org) + [W3C SKOS](https://www.w3.org/TR/skos-reference/).

## Honest limits (Tier A)

- Retrieval's lexical leg is TF-IDF (swap embeddings behind the same `retrieve()` seam).
- Extraction is deterministic (frontmatter + wikilinks + inline relation cues). Inline relation
  **direction** is not resolved ("X superseded by [[Y]]" connects X↔Y but doesn't encode who
  supersedes whom); precise relation extraction is the **Tier-3 LLM** job (injectable `llm_fn`, off
  by default).
- No RDF/OWL/SPARQL/graph-DB yet — that's **Tier B**. No community-summary global search yet.

Built by **Jeff Otterson** ([Jott2121](https://github.com/Jott2121)). Sibling to
[rag-guard](https://github.com/Jott2121/rag-guard). MIT.
