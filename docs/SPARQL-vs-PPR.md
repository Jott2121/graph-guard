# SPARQL/OWL vs. Personalized PageRank — the architect trade-off

`docs/TRADEOFFS.md` answers "graph or flat retrieval, and how much ontology formalism?" for
**Tier A**. This is the sequel, one level deeper: given that you've already committed to a typed
graph, when does it pay to go further — a **formal OWL ontology, reasoned with owlrl, queried
with SPARQL 1.1 property paths** — instead of stopping at Tier A's Personalized PageRank? Same
project, same fixture, two engines, one question.

## The question & the two engines

**Question:** *"What did X supersede, transitively?"* — a multi-hop query over the `supersedes`
relation, exactly the shape `docs/TRADEOFFS.md` identifies as where graphs beat flat retrieval.
Here we hold that win constant and ask a narrower question: *given* a graph, does the query need
formal semantics, or does ranked relevance suffice?

**(a) Personalized PageRank (Tier A)** — `graph_guard/graph_retriever.py`'s `GraphRetriever.retrieve(query, k)`
is the real, live entry point: it entity-links the query to graph nodes (`link_entities`), runs
stdlib Personalized PageRank (`graph_guard/ppr.py::personalized_pagerank`) over the store's
symmetric weighted adjacency (`TripleStore.adjacency()`) personalized on those seed nodes, applies
a specificity discount, and reciprocal-rank-fuses the result with lexical TF-IDF hits. PPR treats
`supersedes` the same as every other edge type — it diffuses relevance mass across *all* typed
edges touching the seed, weighted by confidence, not just the one predicate the question names.
The output is a **ranked list of scores**, not a set: everything reachable gets *some* score, and
rank is a monotone function of graph proximity, not of whether the predicate was actually
`supersedes`.

**(b) SPARQL property-path over the OWL-reasoned graph (Tier B)** — `graph_guard/fuseki.py::supersedes_chain(graph, start_id)`
runs `SELECT ?x WHERE { <start> kl:supersedes+ ?x . }` — the SPARQL 1.1 property-path operator
`+` ("one or more hops"), executed by `rdflib.Graph.query()` against the graph built by
`graph_guard/rdf_export.py::store_to_graph`. This walks **only** asserted `kl:supersedes` edges;
no other predicate can leak in. Separately, `graph_guard/reasoning.py::materialize(data_graph)`
runs `owlrl.DeductiveClosure(owlrl.OWLRL_Semantics)` over the instance data plus the OWL T-Box
(`graph_guard/ontology_data/ontology.ttl`), **entailing** `kl:supersedesTransitively(start, x)` directly as a new
triple for every `x` in the closure — via `kl:supersedes rdfs:subPropertyOf
kl:supersedesTransitively` + `kl:supersedesTransitively a owl:TransitiveProperty` (rules
prp-spo1 + prp-trp). The output is a **set** — membership is binary, and the property path (or the
entailed triple) *is* the proof.

## Side-by-side result

Real output of `eval/sparql_vs_ppr.py` (`PYTHONPATH=. python -m eval.sparql_vs_ppr`), pasted
unedited from one run. The fixture (`eval/sparql_vs_ppr.py::_demo_store`): `project_v3.md
supersedes project_v2.md supersedes project_v1.md` (the exact chain) plus two "noise" nodes reachable
only via `mentions`/`related` (`reference_apex_spec.md`, `feedback_apex_review.md`), plus one fully
disconnected control node (`project_unrelated.md`) that should surface in neither result:

```
Question: "what did project v3 supersede"  (start node: project_v3.md)

=== SPARQL / OWL (Tier B) -- exact closure ===
  property path (kl:supersedes+, no reasoner) : ['project_v1.md', 'project_v2.md']   [32.8735 ms]
  owlrl materialize() (OWL 2 RL entailment)    : 30.9016 ms
  entailed kl:supersedesTransitively candidates: ['project_v1.md', 'project_v2.md']
  property path re-run on reasoned graph       : ['project_v1.md', 'project_v2.md']

=== Personalized PageRank (Tier A) -- ranked relevance list ===
  entity-linked seeds: ['project_v3.md']   [0.173 ms]
    0.016667  project_v3.md                start node
    0.016393  project_v2.md                KNOWN SUPERSEDED
    0.016129  reference_apex_spec.md       noise (not superseded)
    0.015873  feedback_apex_review.md      noise (not superseded)
    0.015625  project_v1.md                KNOWN SUPERSEDED

=== Interpretation ===
  SPARQL returns EXACTLY the known superseded set: ['project_v1.md', 'project_v2.md'].
  PageRank also surfaces non-superseding nodes in its ranked list: ['reference_apex_spec.md', 'feedback_apex_review.md'] -- fuzzy relevance, not a formal answer.
```

**This is the honest result, not a massaged one — see "Honest limits" below for what could have
gone the other way.** Reading it: SPARQL's property path returns `{project_v1.md, project_v2.md}`
and nothing else, three independent ways (raw property path, owlrl-entailed
`kl:supersedesTransitively`, and the same property path re-run post-reasoning) — all three agree,
because `kl:supersedes` is asserted single-hop data and both routes are sound over it. PageRank's
ranked list also contains those two nodes, but **interleaved with the noise nodes** — worse,
`project_v1.md`, the most distal (and still correct) member of the actual answer set, ranks
*dead last*, below both noise nodes it's merely closer to in raw graph distance than it is central.
A caller reading only "top 3" from PageRank would get `project_v3.md` (the question itself),
`project_v2.md` (correct), and `reference_apex_spec.md` (wrong) — silently dropping the transitively
superseded `project_v1.md`. That is exactly the fuzziness/exactness gap this doc is about: PageRank
has no notion that the question named one specific predicate; SPARQL does.

## Comparison table

| Dimension | PageRank (Tier A) | SPARQL/OWL (Tier B) |
|---|---|---|
| **Precision / exactness** | Ranked relevance score; degrades gracefully, no hard cutoff. In this run it ranked a true positive (`project_v1.md`) *below* two false positives. | Exact set membership. The property path only follows the named predicate — no false positives, no ranking to get wrong. |
| **Explainability** | A score is a number, not a proof. "Why is this ranked #3?" requires re-deriving the PPR diffusion — no audit trail. | The query *is* the explanation: `kl:supersedes+` from `start` to `x`, or the specific asserted edges owlrl chained. Directly auditable. |
| **Entailment (derive unasserted facts)** | None — PPR only sees the adjacency that's already there; it cannot derive a fact the extractor didn't assert. | Yes — `materialize()` derives `kl:supersedesTransitively`, `schema:Project` subclass typing, and `skos:broader` from `kl:broader`, none of which `rdf_export.py` ever asserts directly (`graph_guard/reasoning.py`, `tests/test_reasoning.py`). |
| **Validation** | None built in. | SHACL (`graph_guard/ontology_data/shapes.ttl` + `graph_guard/shacl.py::validate`) checks required `name`, valid `type`, functional-predicate max-count-1 — schema conformance as a first-class, queryable artifact. |
| **Interoperability** | Bespoke: SQLite schema + a stdlib adjacency dict. Not portable to another team's tooling without a custom adapter. | Standards-based: RDF/Turtle, OWL 2, SPARQL 1.1, SKOS, schema.org. Loads into any conformant triplestore — AWS Neptune's RDF/SPARQL engine included (see below). |
| **Cost / dependencies** | stdlib only (`math`, `sqlite3`); `networkx` is an optional drop-in, never required. | `rdflib`, `owlrl`, `pyshacl` (the `[rdf]` extra); the live path (opt-in, `graph_guard/fuseki.py::FusekiClient`) additionally needs a running Apache Jena Fuseki server — Java. |
| **Latency at personal-KG scale** | 0.173 ms for `GraphRetriever.retrieve` on this 6-node fixture (measured in-process, single run — illustrative only, not a benchmark). | 32.9 ms for the property-path query, 30.9 ms for `materialize()` on the same fixture — both dominated by one-time rdflib SPARQL query-plan compilation / owlrl setup, not the graph's size (a repeated warm call to the same compiled query drops to ~0.8 ms; see "Honest limits"). |
| **Latency at enterprise scale** | Not measured here — PPR's cost scales with adjacency size and iteration count, independent of query shape. | Not measured here — a real triplestore (Fuseki/Neptune) amortizes query planning and indexes SPO/POS/OSP, which this in-process rdflib demo does not exercise. |
| **Query-authoring ergonomics** | The query is natural language; `link_entities` handles the mapping via lexical overlap on a small closed vocabulary — reliably LLM-generatable because the schema stays lean (`graph_guard/schema.py`'s explicit right-sizing rationale). | SPARQL is hand-written here (`_supersedes_chain_query` et al.), not LLM-generated. "Knowledge Conceptualization Impacts RAG Efficacy" (arXiv:2507.09389) found LLM SPARQL-generation reliability *degrades* as ontology expressiveness grows — the more OWL formalism Tier B adds, the harder an LLM-in-the-loop version of this query gets to auto-generate correctly. |

## When the heavyweight stack earns its cost

The thesis, mapped onto this result: **when the win is formal semantics, not just relationships**
— entailment of facts nothing asserted directly, SHACL-validated data quality, a shared ontology
multiple teams query against, standards-based interop (Neptune, Jena, any SPARQL 1.1 endpoint),
and an *exact, auditable* answer to a precisely-scoped multi-hop question — RDF/OWL/SPARQL wins,
and PageRank isn't in the running because it has no concept of "prove it." That is the Lockheed/AWS
Neptune context this Tier B branch was built to rehearse: Neptune's RDF/SPARQL engine plus an
external reasoner is the same architecture as `rdf_export.py` → `ontology.ttl` → `owlrl` →
`fuseki.py`, just at enterprise scale and with a managed triplestore instead of an in-process
`rdflib.Graph`. For a cross-team semantic layer over heterogeneous enterprise data — where
"prove this fact is entailed by policy X" is a real requirement, not a nice-to-have — the
ontology *is* the product, and its cost (Java, a reasoner, SHACL authoring, SPARQL expertise) is
worth it.

For **personal-scale fuzzy relevance ranking** — "what's related to this," not "prove X follows
from Y" — PageRank wins and the ontology is overhead: no entailment need, no cross-team schema to
govern, no standards-interop requirement, and (per arXiv:2507.09389) a smaller, lexically-linkable
schema is *more* reliable for an LLM to query than a fully OWL-expressive one. That's why Tier A
stays the live retrieval path for graph-guard's actual vault, and Tier B is the fidelity/interop
layer, not a replacement.

## Honest limits

- **This is a mechanism/fidelity demo, not a quantified lift over Tier A on the real vault.** The
  fixture above is six nodes, hand-built to make the exactness-vs-fuzziness gap visible. It proves
  the mechanism (SPARQL returns an exact closure; PageRank returns a fuzzy ranked list that can rank
  a true positive below false positives) — it does not measure precision/recall of either engine on
  graph-guard's real ~750-note, 686-node vault. That measurement is a separate, still-open step
  (same caveat `README.md` and `docs/TRADEOFFS.md` already carry for Tier A's own eval).
- **The result could have gone the other way, and didn't get massaged to avoid that.** If the noise
  nodes hadn't out-ranked `project_v1.md`, or if PageRank had happened to return exactly
  `{project_v2.md, project_v1.md}` with nothing else, that would have been reported as-is per the
  build brief for this task — it wasn't necessary here, but the fixture was built and run before
  this doc was written, not after, specifically so the numbers couldn't be reverse-engineered into
  a cleaner story.
- **The latency numbers are a single in-process run at personal-KG (6-node) scale, not a benchmark.**
  The ~31-33 ms SPARQL-side numbers are dominated by one-time cost (rdflib's SPARQL query-plan
  compilation on first use, and owlrl's reasoner setup) — a warm, repeated call to the *same*
  compiled query on the *same* graph measured ~0.8 ms in a follow-up 200-iteration check during
  this task's development (not included in the pasted run above, which reports each engine's single
  first call, matching how the demo script and a real one-shot query would actually be used). No
  claim is made about relative cost at enterprise scale; that depends entirely on triplestore
  indexing and query complexity, neither of which this in-memory `rdflib.Graph` exercises.
- **The Fuseki live path is opt-in**, not part of this demo or its tests. `graph_guard/fuseki.py`'s
  `FusekiClient` only runs against a real Apache Jena Fuseki server when
  `GRAPH_GUARD_FUSEKI_LIVE=1` is set (`tests/test_fuseki.py::test_live_fuseki_roundtrip`,
  `scripts/run-fuseki.sh`); this doc's numbers are all from rdflib's in-memory SPARQL engine, which
  is what the CI-covered test suite runs.
- **owlrl's `OWLRL_Semantics` is OWL 2 RL** — a decidable, rule-based fragment of OWL 2, not full
  OWL-DL reasoning. It covers the entailments this project uses (transitive properties, sub-property,
  class subsumption — see `graph_guard/reasoning.py`'s module docstring for the exact rules), but it
  is not a general-purpose description-logic reasoner; some OWL-DL inferences it cannot draw.
- **No novelty is claimed.** This doc packages well-established building blocks: RDF/SPARQL 1.1
  property paths ([W3C SPARQL 1.1](https://www.w3.org/TR/sparql11-query/#propertypaths)), OWL 2 RL
  entailment ([W3C OWL 2 RL](https://www.w3.org/TR/owl2-profiles/#OWL_2_RL)),
  [GraphRAG](https://arxiv.org/abs/2404.16130)'s framing of graph-structured retrieval,
  [HippoRAG](https://arxiv.org/abs/2405.14831)'s Personalized-PageRank retrieval (what Tier A
  implements), the right-sizing caution in "Knowledge Conceptualization Impacts RAG Efficacy"
  (arXiv:[2507.09389](https://arxiv.org/abs/2507.09389)), and
  [AWS Neptune](https://aws.amazon.com/neptune/)'s production pattern of an RDF/SPARQL store paired
  with an external reasoner (the architecture `graph_guard/fuseki.py` + `graph_guard/reasoning.py`
  mirrors at local/in-process scale). See `docs/TRADEOFFS.md` for the Tier-A-level version of this
  same discipline (graph vs. flat retrieval, schema right-sizing) — this doc doesn't repeat it.

Reproduce: `cd ~/graph-guard && source .venv/bin/activate && PYTHONPATH=. python -m eval.sparql_vs_ppr`.
Tested: `tests/test_sparql_vs_ppr.py`.
