# graph-guard

![ci](https://github.com/Jott2121/graph-guard/actions/workflows/ci.yml/badge.svg)
![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)
![tests](https://img.shields.io/badge/tests-137-brightgreen.svg)
![coverage](https://img.shields.io/badge/coverage-97%25-brightgreen.svg)

**A knowledge graph that makes RAG answer the hard questions — the ones where the
answer is spread across several documents — plus a measured, honest account of when
the heavyweight semantic stack is worth its cost and when it isn't.**

Most RAG retrieval matches on *similarity*: it finds text that sounds like your
question. That works for a direct lookup and breaks the moment the answer spans
several documents, because no single passage looks like the whole question — and
those connected questions are usually the ones worth asking. graph-guard puts a
typed **knowledge graph** behind the retriever so it can follow the *connections
between facts* (multi-hop).

Then it does the honest part, and the honest part is a negative result:

> **On a real 586-note corpus, scored against what 83 real working sessions actually
> opened — with a positive control and a shuffled-gold negative control that both pass —
> the graph did not beat plain chunk-level TF-IDF. Nor did the ontology on top of it.
> The lexical baseline won.**

That is not the result this repo originally reported, and the difference is the whole
lesson. The original **+14% hit@10 / +26% MRR** headline was measured on *structure-derived
probes* — queries synthesized from the graph's own edges, with the linked note as the gold
answer. A graph will always win that benchmark, because the benchmark is built from the
mechanism under test. It is circular, and it said nothing about the questions a human
actually asks. Those numbers, and the method, are preserved below and in
[`docs/EVAL-real-vault-lift.md`](docs/EVAL-real-vault-lift.md) — not deleted, because the
comparison between the two evals is more useful than either one alone.

**What it costs to find this out:** a cached graph silently degraded to 2 nodes (see
[the staleness bug](#the-cache-bug-that-hid-all-of-this)) and, because the retriever falls
back to lexical when a query links to no anchor, a full day of measurements was attributed
to a graph that was not running. *A component that fails silently on a stale cache gets
measured as working.* `service.graph_health()` exists so you can assert otherwise.

## Try it (no API key, no model)

```bash
pip install -e .
python examples/run_sample.py
```

Runs the whole pipeline over 7 tiny notes and shows the graph surfacing the *owner* of a
bug that lexical search scores **0.00** — because her note shares no words with the query,
but the graph reaches her in two hops. Deterministic, no model call. See
[`examples/`](examples/) for the walkthrough.

## The measured result

### Against real sessions (the eval that matters)

[`eval/real_sessions_ab.py`](eval/real_sessions_ab.py) takes its labels from **outside** the
system under test. For each Claude Code session it uses the first substantive user prompt as
the query, and the notes that session went on to **open** as the gold set. Weak, but
independent — and biased *toward* breadth-seeking methods, since the gold set spans
everything the session needed while the query is only its opening prompt. A method that
surfaces the rest of a spread-out answer should win under this label. That is what makes a
loss here meaningful.

**Two pre-registered controls run first, and the eval aborts if either fails.** Every
methodology error in this repo's history was a *harness* bug, not an analysis bug, so a
number is not reportable until the harness has shown it can both detect a signal and lose
one:

| control | requires | measured |
|---|---|---|
| **positive** — query a note with its own verbatim text | recovers that note | **25/25 (100%)** |
| **negative** — shuffle gold sets across sessions | recall collapses | **0.2499 vs 0.6731 real (ratio 0.37)** |

The shuffled floor is worth reading directly: roughly **a quarter of "recall" here is base
rate**, not relevance — a handful of notes are opened in many sessions. Judge every arm below
against 0.25, not against 0.

586-note corpus, 913 nodes / 2,101 edges, 83 labelled sessions, 81 of which link to at least
one graph anchor. recall@20, paired sign test against the no-graph ensemble:

| arm | recall@20 | vs ensemble |
|---|---|---|
| **flat** (chunk-level TF-IDF) | **0.6731** | better 11, worse 10, p=1.00 |
| note-level TF-IDF | 0.6363 | better 3, worse 10, p=0.092 |
| ensemble (note + chunk, no graph) | 0.6598 | baseline |
| **ensemble + PageRank** | 0.6437 | better 1, worse 5, p=0.22 |

**Nothing beat plain chunk-level TF-IDF, and adding the graph made the ensemble slightly
worse.** No difference here is significant at n=82, so the defensible claim is not "the graph
hurts" — it is that **on this corpus, with these labels, the graph produced no measurable
benefit**, while costing a build step, a cache, and a second retrieval system in the path.

Reproduce on your own notes:

```bash
python eval/real_sessions_ab.py --roots ~/notes --transcripts ~/.claude/projects/<project>
```

Output is aggregate-only — no prompts, no filenames, no session ids.

### The cache bug that hid all of this

`build_retriever` used to treat the cached graph as fresh whenever it had any edges at all
(`edges == 0` was the only staleness test). One stale edge blocked rebuild permanently. A
cache holding **2 nodes and 1 edge** against a ~590-note corpus therefore persisted
indefinitely — and since `GraphRetriever` falls back to pure lexical whenever a query links
to no anchor (a deliberate hybrid behaviour), it kept answering plausibly and reported
nothing wrong. Fixed: the graph now records the corpus fingerprint it was built from, and
`service.graph_health(retriever)` returns `{nodes, edges, empty}` so a caller can assert a
graph is actually loaded before attributing anything to it. The eval aborts if it is empty.

### Against structure-derived probes (the original, circular eval — kept for contrast)

Three arms — flat TF-IDF, the Tier-A typed graph, the Tier-B owlrl-reasoned graph — over 517
notes / 807 nodes / 1,814 edges, scored on 159 **structure-derived** multi-hop probes and 517
simple-lookup probes (k=10). Method in
[`docs/EVAL-real-vault-lift.md`](docs/EVAL-real-vault-lift.md), raw numbers in
[`eval/results.json`](eval/results.json).

| Finding | Result |
|---|---|
| Graph beats flat on multi-hop | hit@10 0.3145 → 0.3585 (+14% rel); MRR 0.1303 → 0.1647 (+26% rel) |
| Graph doesn't hurt simple lookups | within ~1 point of flat on every metric |
| owlrl reasoning adds ~zero retrieval lift | hit@10 identical to raw graph; MRR +0.0008 |

**These numbers are invalid by construction and are retained only to show what a
structure-derived probe reports.** The probes are generated from the graph's own edges, so
the graph is asked to walk connections the probe generator just showed it. Note the wording:
they are *not* an "upper bound" — a circular benchmark has no bounding property in either
direction, since it measures the structure it was derived from and can overstate or
understate arbitrarily. Calling it a bound would be an invalid measurement wearing
valid-sounding language, which is the exact failure this section exists to document. The contrast with the session
eval above is the most useful thing in this repo: *the same system, measured two ways, gives
opposite answers, and only one of the two used labels the system didn't author.*

The Tier-B conclusion survives both evals and is unchanged: the ontology earns its cost on
fidelity, SHACL validation, entailment, and standards interop (SPARQL, and by extension AWS
Neptune) — **not** on retrieval. See [`docs/TRADEOFFS.md`](docs/TRADEOFFS.md) and
[`docs/SPARQL-vs-PPR.md`](docs/SPARQL-vs-PPR.md).

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

- **The structure-derived probes are circular** and should not be read as real-world lift: a
  probe's query is a note's own label and its gold answer is a note linked to it, so the graph is
  scored on walking edges the probe generator handed it. The session eval exists because of this.
- **The session eval is weakly labelled too**, in the other direction: gold is every corpus note a
  session opened, while the query is only its first prompt, so it credits methods for surfacing
  things the user needed later. It also runs retrieval over *today's* corpus, not the corpus as it
  stood during that session. Both biases favour the graph, which is why the null result stands.
- **Single-gold** assumption; real queries can have several relevant notes.
- A **personal N-of-1 vault** (the author's own ~586 notes) — these results may not generalize to
  a different corpus, domain, or scale. **n=82 sessions is small**: no arm difference in the
  session eval reaches significance, so the honest claim is "no measurable benefit", not "harmful".
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
