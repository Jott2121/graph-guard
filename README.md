# graph-guard

![ci](https://github.com/Jott2121/graph-guard/actions/workflows/ci.yml/badge.svg)

**Ontology/graph-aware retrieval over a personal knowledge vault — built in two tiers plus a
real-vault measurement of what each one buys you.** Turns a folder of markdown (Obsidian
`[[wikilinks]]` + YAML frontmatter) into a typed knowledge graph, retrieves with multi-hop
**Personalized PageRank fused with lexical TF-IDF** behind
[rag-guard](https://github.com/Jott2121/rag-guard)'s `retrieve()` seam, and — as a Tier-B fidelity
layer — exports the same graph as a formal **RDF/OWL/SHACL/SPARQL** ontology with owlrl reasoning.

The point isn't "graph vs. vectors" or "how much OWL can we bolt on." It's **judgment**: knowing
*when* the heavyweight semantic stack earns its cost and when it doesn't — shown with numbers
measured on a real, live 517-note vault, not a toy benchmark.

## The measured result

Three retrieval arms — flat TF-IDF, the Tier-A typed graph, and the Tier-B owlrl-reasoned graph —
run over graph-guard's actual knowledge graph (517 notes / 807 nodes / 1,814 edges), scored on 159
structure-derived multi-hop probes and 517 simple-lookup probes (k=10). Full method and honest
limits in [`docs/EVAL-real-vault-lift.md`](docs/EVAL-real-vault-lift.md); raw numbers in
[`eval/results.json`](eval/results.json).

| Finding | Result |
|---|---|
| **Graph beats flat on multi-hop** | hit@10 0.3145 → 0.3585 (**+14% relative**); MRR 0.1303 → 0.1647 (**+26% relative**) |
| **Graph doesn't hurt simple lookups** | within ~1 point of flat on every metric — the hybrid fallback holds |
| **owlrl reasoning adds ~zero retrieval lift** | hit@10 identical to raw graph (0.3585 both); MRR +0.0008 |

**The takeaway:** the ontology earns its cost on fidelity, SHACL validation, entailment, and
standards interop (SPARQL, and by extension AWS Neptune) — **not** on retrieval. That's not a
weakness of Tier B, it's the honest shape of what formal semantics is *for*. See
[`docs/TRADEOFFS.md`](docs/TRADEOFFS.md) (graph-vs-flat, how much ontology) and
[`docs/SPARQL-vs-PPR.md`](docs/SPARQL-vs-PPR.md) (the exactness-vs-fuzziness mechanism behind
that third finding) for the full architect reasoning.

## The three layers (all shipped)

- **Tier A — working core.** A typed knowledge graph (SQLite triples, provenance + confidence)
  with multi-hop Personalized PageRank fused with lexical TF-IDF, hybrid-routed, behind
  rag-guard's `retrieve()` seam. Lean closed schema; graph-tightened guards. Near-stdlib, fast,
  fully tested.
- **Tier B — enterprise-fidelity layer.** The *same* graph, exported as a formal ontology:
  RDF/Turtle with reified provenance, an OWL T-Box (schema.org/SKOS-mapped, with a **DL-safe
  functional-vs-transitive `supersedes` split**), SHACL shapes, SPARQL 1.1 (rdflib in-memory,
  fully tested; opt-in Apache Jena Fuseki for a live server), and owlrl OWL-2-RL
  reasoning/entailment. This mirrors the architecture AWS Neptune uses in production — an
  RDF/SPARQL store plus an external reasoner — documented in `docs/SPARQL-vs-PPR.md`.
- **Gate D — the measurement.** A 3-arm eval (flat / graph / owlrl-reasoned) over the real vault,
  with structure-derived probes (no hand labeling) and an aggregate-only, PII-safe output — the
  numbers above.

## How it works

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

**Tier B path:** `rdf_export.py` turns the live `TripleStore` into RDF/Turtle (`ontology_data/
ontology.ttl` is the OWL T-Box, `ontology_data/shapes.ttl` the SHACL shapes) → `shacl.py::validate`
checks conformance → `reasoning.py::materialize` runs owlrl OWL-2-RL entailment → `fuseki.py`
runs SPARQL 1.1 (property paths included) against the in-memory graph, or an opt-in local Fuseki
server.

## Install / run

```bash
pip install "git+https://github.com/Jott2121/graph-guard.git"   # pulls guarded-rag from git automatically
```

For development:

```bash
pip install -e ".[dev,rdf]"    # [rdf] adds rdflib/pyshacl/owlrl for Tier B
python -m pytest -q            # 137 passing (+1 opt-in Fuseki skip), ~97% coverage, Python 3.11-3.13 (see .github/workflows/ci.yml)
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

**Reproduce the measured lift** against your own vault: `python -m eval.real_vault_lift` (reads a
local vault via `rag_guard.config.default_roots()`; writes an aggregate-only, PII-safe
`eval/results.json` — no note ids, paths, or query/gold text). The mechanism demo behind the
"owlrl adds ~zero lift" finding: `python -m eval.sparql_vs_ppr`.

## Where this sits in the landscape (prior art)

None of the ideas are novel — the value is the integration and the honest right-sizing judgment.
Retrieval lineage: [GraphRAG](https://arxiv.org/abs/2404.16130) (local/global/community
summaries), [LightRAG](https://arxiv.org/abs/2410.05779) (lightweight dual-level),
[HippoRAG](https://arxiv.org/abs/2405.14831) (Personalized PageRank multi-hop),
[OG-RAG](https://arxiv.org/abs/2412.15235) (ontology-grounded), the
[Personal Knowledge Graph survey](https://arxiv.org/abs/2304.09572), and
[GraphRAG-Bench](https://arxiv.org/abs/2506.05690) (graphs win on multi-hop, not simple lookups —
matches this repo's own measurement). Right-sizing: "Knowledge Conceptualization Impacts RAG
Efficacy" ([arXiv:2507.09389](https://arxiv.org/abs/2507.09389)). Standards: schema.org, W3C
[SKOS](https://www.w3.org/TR/skos-reference/), [OWL 2](https://www.w3.org/TR/owl2-profiles/#OWL_2_RL),
[SPARQL 1.1](https://www.w3.org/TR/sparql11-query/#propertypaths). Production analogue:
[AWS Neptune](https://aws.amazon.com/neptune/)'s RDF/SPARQL engine plus an external reasoner.

## Honest limits

- The eval's structure-derived probes measure multi-hop **link-recovery and no-harm**, not organic
  question relevance — a probe's query is a note's own label, not something a user actually typed.
- **Single-gold** assumption; real queries can have several relevant notes.
- A **personal N-of-1 vault** (the author's own ~517 notes) — these results may not generalize to
  a different corpus, domain, or scale.
- The numbers are a **snapshot** (2026-07-02): the vault is live and evolves, so a re-run will
  drift even though the measurement itself is deterministic for a fixed snapshot.
- **owlrl is OWL 2 RL** — a decidable, rule-based fragment of OWL 2, not full OWL-DL reasoning.
- Retrieval's lexical leg is TF-IDF (swap embeddings behind the same `retrieve()` seam).
- Extraction is deterministic (frontmatter + wikilinks + inline relation cues). Inline relation
  **direction** is not resolved ("X superseded by [[Y]]" connects X↔Y but doesn't encode who
  supersedes whom); precise relation extraction is the **Tier-3 LLM** job (injectable `llm_fn`,
  off by default). No community-summary global search yet.
- The Fuseki live path is opt-in (`GRAPH_GUARD_FUSEKI_LIVE=1`), not part of the default test run.

Built by **Jeff Otterson** ([Jott2121](https://github.com/Jott2121)). Sibling to
[rag-guard](https://github.com/Jott2121/rag-guard). MIT.
