# graph-guard — Tier A (working ontology/graph retriever) — spec + plan

**Date:** 2026-07-01 · **Status:** design approved (hybrid; lean/right-sized schema; local-first) · build pending
**Delivery:** Sonnet 5 implements test-first; Opus judges each task. **Consumes** rag-guard via its
`retrieve()` seam; does not modify rag-guard.

## Goal
Upgrade retrieval over Jeff's Obsidian vault from flat TF-IDF to an **ontology/graph-aware**
retriever that wins on multi-hop / relational / thematic queries, reusing what already exists:
`[[wikilinks]]` = a proto-graph, YAML frontmatter + filename prefixes = proto-schema. Plug it behind
rag-guard's `retrieve(query, k) -> [{id,text,score}]` contract so the pipeline + guards are untouched,
and tighten grounding with the graph.

## Locked decisions
- **Hybrid**, Tier A first (working core), Tier B later (RDF/OWL/SPARQL on local Jena).
- **Lean, right-sized schema** on the live path (closed predicate set) — full OWL lives in Tier B.
- New repo `~/graph-guard`; Tier A core is stdlib + `guarded-rag` (optional `networkx` upgrade).
- Read-only over the vault (extraction never writes to notes).

## Architecture (Tier A)
```
Obsidian vault (frontmatter + [[wikilinks]] + prose)
        │  extract.py  (3-tier, fingerprint-gated, incremental)
        ▼
   SQLite triple store  (store.py: nodes + edges, provenance + confidence)
        │  load → in-memory adjacency
        ▼
   GraphRetriever.retrieve(query,k)   (graph_retriever.py)
     entity-link query → Personalized PageRank (ppr.py) → rank nodes →
     map to note chunks → reciprocal-rank fuse with rag-guard TF-IDF →
     hybrid route (simple lookup → TF-IDF; multi-hop/thematic → graph)
        ▼
   rag-guard pipeline + tightened guards (guards.py)
     entity/relation-overlap grounding · zero-node structural refuse · functional-predicate contradiction
```

## Schema (lean, closed) — `schema.py`
- **Entity types** (mapped to schema.org/SKOS in Tier B export): `Person, Project, Reference,
  Feedback, Decision, Claim, Source, Tool, Event, Concept`. Node type is inferred from filename
  prefix (`project_`, `reference_`, `feedback_`, `user_`) and/or frontmatter `type:`; default `Note`.
- **Closed predicate set:** `mentions` (from a bare wikilink), `about` (→Concept/tag), `is_part_of`
  (→Project), `authored_by`/`created_by` (→Person), `supersedes` (Decision→Decision), `blocks`/
  `depends_on`, `decides`, `supports`/`refutes` (Source→Claim), `derived_from` (provenance),
  `broader`/`narrower`/`related` (SKOS, tag taxonomy).
- Helpers: `node_type(note_id, frontmatter) -> str`; `is_valid_predicate(p) -> bool`;
  `FUNCTIONAL = {"has_status", "supersedes"}` (single-valued → used for contradiction checks).

## Data shapes (contracts every task shares)
- **Node:** `{"id": str, "type": str, "name": str, "note_path": str, "attrs": dict}`
- **Edge:** `{"src": str, "predicate": str, "dst": str, "note_path": str, "span": str|None,
  "confidence": float, "extractor": str}` (extractor ∈ `frontmatter|wikilink|llm`)
- **Retriever hit (unchanged from rag-guard):** `{"id": str, "text": str, "score": float}`

## Tasks (each: TDD red→green→commit; Opus review between)
- **T1 `schema.py`** — entity/predicate vocab + `node_type`, `is_valid_predicate`, `FUNCTIONAL`.
- **T2 `store.py`** — SQLite `nodes`/`edges` tables; `upsert_node/edge`, `neighbors(node,dir)`,
  `all_edges()`, `adjacency()` (dict-of-dicts for PPR), `save/load` a `~/.cache/graph-guard/kg.sqlite`.
- **T3 `extract.py`** — `extract_note(note_id, text, frontmatter) -> (nodes, edges)`: Tier1 frontmatter
  (deterministic), Tier2 wikilinks (deterministic, heading-typed), Tier3 `llm_fn` (injectable,
  schema-constrained; default None → skip). `build_graph(roots, store, *, llm_fn=None)` walks the
  corpus (reuse `rag_guard.corpus`/`config`), fingerprint-gated incremental.
- **T4 `ppr.py`** — stdlib Personalized PageRank over an adjacency dict (`personalized_pagerank(adj,
  seeds, alpha=0.85, iters=30) -> {node: score}`); node-specificity down-weighting (degree/IDF-style).
- **T5 `graph_retriever.py`** — `GraphRetriever(store, tfidf_retriever)` with
  `retrieve(query, k=5) -> [{id,text,score}]`: entity-link query → PPR → node→chunk → RRF-fuse with
  `tfidf_retriever.retrieve`; `link_entities(query) -> [node_ids]`; hybrid route.
- **T6 `guards.py`** — `graph_groundedness(answer, subgraph) -> {grounded, support}` (entity/relation
  overlap); `should_refuse_structural(query, linked_nodes) -> bool`; `contradicts_local(answer_triples,
  store) -> bool` (functional-predicate conflict).
- **T7 `service.py` + `build_cli.py`** — warm singleton `query(text,k)`; `graph-guard-build` CLI to
  (re)build the KG; fingerprint-gated.
- **T8 eval + README** — multi-hop eval set proving graph beats flat on relational queries; README
  with the honest prior-art framing (GraphRAG/LightRAG/HippoRAG/schema.org/SKOS) + the Tier-A/B
  tradeoff writeup (the architect signal).

## Guard tightening (the payoff)
- **Grounding:** replace token-overlap with **entity+relation overlap** — each asserted triple in the
  answer must be backed by an edge in the retrieved subgraph.
- **Refuse:** if the query links to **zero known nodes**, refuse even if TF-IDF spikes on one rare word
  (fixes rag-guard's documented out-of-corpus false-accept).
- **Contradiction:** for functional predicates (`has_status`, `supersedes`), if the answer asserts an
  object conflicting with the stored one → flag (makes `contradicts_local` real).

## Testing
- TDD per task; **LLM extraction mocked** for determinism (default `llm_fn=None` uses only Tier1/2).
- Multi-hop eval: seed a tiny synthetic vault with a known relation chain; assert GraphRetriever pulls
  the one-hop-away answer that flat TF-IDF misses.
- Coverage gate ≥90% on `graph_guard`.

## Non-goals (Tier A)
- No RDF/OWL/SPARQL/graph-DB (that's Tier B). No embeddings (TF-IDF stays the lexical leg).
- No writes to the vault. No community-summary global search yet (fast-follow after T5).
