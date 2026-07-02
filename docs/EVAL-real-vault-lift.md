# Real-vault retrieval lift — does the graph (and reasoning) actually help?

`docs/TRADEOFFS.md` argues, qualitatively, that a typed graph beats flat lexical retrieval on
multi-hop queries and that formal OWL reasoning is worth paying for only outside retrieval
(fidelity, validation, interop). `docs/SPARQL-vs-PPR.md` demonstrates the exactness-vs-fuzziness
mechanism on a hand-built six-node fixture and says plainly that it is "a mechanism/fidelity
demo, not a quantified lift over Tier A on the real vault." This doc closes that gap: it runs the
three retrieval arms — flat TF-IDF, the Tier-A typed graph, and the Tier-B owlrl-reasoned graph —
over graph-guard's actual, live knowledge graph and reports what the numbers say, including the
one that doesn't flatter the ontology.

## The question

Does the typed-graph layer measurably improve retrieval over flat lexical search on the real
vault, and does owlrl reasoning add anything on top of raw Personalized PageRank? Tier A and
Tier B each shipped this as an open caveat — "mechanism proven, real-vault lift unquantified."
This is that measurement.

## Method

### The three arms

- **flat** — `rag_guard.retriever.Retriever`, pure TF-IDF over the vault's `.md` files. The
  baseline every other arm is measured against.
- **graph** — `graph_guard.graph_retriever.GraphRetriever.retrieve` (Tier A, unchanged):
  entity-links the query to graph nodes, runs `graph_guard/ppr.py`'s stdlib Personalized
  PageRank over `TripleStore.adjacency()` (the KG's asserted, confidence-weighted edges),
  applies a specificity discount, and reciprocal-rank-fuses the result with the flat arm's
  TF-IDF hits — the hybrid fallback that returns pure-lexical results when the query links to no
  graph anchor. See `docs/SPARQL-vs-PPR.md` for the full mechanics; this eval reuses that engine
  unmodified.
- **reasoned** — the same `GraphRetriever`, but with PPR run over the adjacency built by
  `graph_guard/reasoned_graph.py::reasoned_adjacency`: owlrl (`OWLRL_Semantics`) materializes
  the graph, and every asserted edge is kept at its original confidence weight while only the
  **genuinely new** entailed note-to-note edges (the transitive-supersedes closure, SKOS
  `broader` rollups, etc., excluding `rdf:type`/`schema:name`/the reification vocabulary) are
  added at a uniform weight. That is: `reasoned = graph + only-what-reasoning-reveals`, by
  design — so any difference between the two arms is attributable to reasoning, not to
  re-weighting or a different retrieval mechanism.

All three arms are built once and share the same underlying store, TF-IDF index, and text map
(`eval/real_vault_lift.py::run`), so no arm gets a different snapshot of the vault.

### The probes — ground truth from the KG's own structure

The vault has no hand-written relevance labels, so `graph_guard/eval_probes.py` derives ground
truth from the graph's own edges — deterministic, no RNG, no manual labeling:

- **multi-hop** (`multi_hop_probes`) — for every KG edge whose predicate is "relational"
  (`schema.PREDICATES` minus `mentions`, which is excluded as too generic to test genuine
  traversal) between two real notes, `query` = the source note's clean label, `gold` = the
  destination note. The probe is kept only if the query and gold clean-label token sets overlap
  by at most one token — the **low-overlap filter**. This is what makes it a multi-hop test:
  flat lexical search cannot win these by word-overlap accident, only a graph edge reaches gold.
  180 probes passed the filter; 5 were discarded for too much lexical overlap (reported, not
  silently dropped).
- **simple-lookup** (`simple_lookup_probes`) — one probe per real note, `query` = the note's own
  clean label, `gold` = that same note. High overlap by construction: the easy control the graph
  must not regress on. 517 probes, one per note in the vault.

### Metrics

`graph_guard/eval_metrics.py::evaluate` runs each arm over every probe, finds the 1-based rank of
`gold_id` in the top-`k` returned ids (k=10 throughout), and aggregates `hit@1`/`hit@5`/`hit@10`
(fraction of probes where gold appears in the top-N) and MRR (mean reciprocal rank, 0 if gold is
absent from the top-k) per family and overall. `lift` reports the absolute per-metric delta
between two arms' metrics, positive or negative, never massaged.

## Results

Real output of `python -m eval.real_vault_lift` over the live vault, pasted from the committed
`eval/results.json`: **517 notes, 807 nodes, 1814 edges**. **180 multi-hop probes, 517
simple-lookup probes** (5 discarded by the overlap filter, not capped). k=10, ~47s runtime.
Probe generation and metric computation are deterministic — a re-run reproduces these numbers.

| arm | family | hit@1 | hit@5 | hit@10 | MRR | n |
|---|---|---|---|---|---|---|
| flat | multi_hop | 0.0611 | 0.2167 | 0.2889 | 0.1218 | 180 |
| graph | multi_hop | 0.0833 | 0.2611 | **0.3500** | **0.1593** | 180 |
| reasoned | multi_hop | 0.0889 | 0.2667 | **0.3500** | **0.1602** | 180 |
| flat | simple_lookup | 0.3849 | 0.6983 | 0.8046 | 0.5251 | 517 |
| graph | simple_lookup | 0.3752 | 0.7060 | 0.8027 | 0.5207 | 517 |
| reasoned | simple_lookup | 0.3791 | 0.7060 | 0.8008 | 0.5233 | 517 |

Lift, from `eval/results.json`:

- **graph vs. flat, multi_hop:** hit@10 **+0.0611** (0.289 → 0.350, +21% relative), MRR
  **+0.0375** (+31% relative), hit@5 +0.0444.
- **graph vs. flat, simple_lookup:** hit@5 +0.0077, hit@10 −0.0019, MRR −0.0044, hit@1 −0.0097 —
  within ~1 point on every metric, i.e. no meaningful harm.
- **reasoned vs. graph, multi_hop:** hit@10 **+0.0** (identical, 0.3500 both), MRR +0.0009,
  hit@5 +0.0056 — essentially zero.

(`eval/results.json` also carries a probe-count-weighted "overall" row pooling both families;
it isn't reproduced above because it mixes two probe families that test different things and the
per-family rows above are what actually answers the question. It's in the committed file for
anyone who wants it.)

### Finding 1 — the graph produces real, measured multi-hop lift

+21% relative hit@10 and +31% relative MRR over flat TF-IDF on 180 structure-derived multi-hop
probes. This quantifies what Tier A and Tier B previously only argued qualitatively
(`docs/TRADEOFFS.md`'s claim "graphs win on multi-hop," and `docs/SPARQL-vs-PPR.md`'s six-node
mechanism demo) with a measurement on the actual, live 517-note vault.

### Finding 2 — the graph does not hurt simple lookups

On the 517 simple-lookup probes the graph arm is within about one point of flat on every metric
(hit@5 slightly up, hit@1/MRR slightly down, hit@10 essentially flat). The hybrid fallback —
pure-lexical when the query links to no graph anchor — is doing its job: it doesn't reproduce the
GraphRAG-Bench-style regression on easy queries that a graph-only retriever would be exposed to.

### Finding 3 — owlrl reasoning adds essentially nothing to retrieval beyond raw PageRank

`reasoned` tracks `graph` on every metric: identical hit@10 on multi-hop (0.3500 both), MRR
+0.0009, hit@5 +0.0056. The likely mechanism: Personalized PageRank already diffuses relevance
mass across multi-hop paths through the raw adjacency, so materializing the transitive-supersedes
closure (or SKOS/subclass edges) as explicit new edges is largely redundant *for ranking
purposes* — PPR was already reaching those nodes through intermediate hops, reasoning just adds a
direct edge to a place PPR's diffusion already touched.

**The architect takeaway:** the ontology's value on this vault is fidelity, SHACL validation,
entailment as an auditable fact, and standards interop (Fuseki/SPARQL, and by extension
Neptune) — not retrieval lift. That is exactly `docs/SPARQL-vs-PPR.md`'s framing of what the
heavyweight stack earns its cost on, now with a retrieval-side number attached: reasoning is free
to add for those other reasons, but it should not be sold as a retrieval upgrade.

## When the graph earns its cost (the decision)

- **Multi-hop / relational retrieval** → the graph earns its keep, measured: +21% relative
  hit@10, +31% relative MRR on this vault's actual multi-hop structure.
- **Simple fact lookups** → flat suffices; the graph is close to free insurance underneath it via
  the hybrid fallback, not a tax on easy queries.
- **owlrl reasoning** → does not pay for itself in retrieval on this vault. It pays for
  fidelity, SHACL-checked data quality, and standards-based interop — the case
  `docs/SPARQL-vs-PPR.md` makes and the Neptune/enterprise-triplestore context it's built to
  rehearse. Route reasoning to where "prove it" matters, not to where "rank it" is the ask.

## Honest limits

- **Structure-derived probes measure multi-hop link-recovery and no-harm, not organic-question
  relevance.** A probe's query is a note's own clean label reaching a linked note; a real user's
  question is not a note title. These numbers say the graph recovers its own link structure
  better than flat does and doesn't regress easy lookups — they do not directly say "users will
  get better answers to the questions they actually ask."
- **Single-gold assumption.** Each probe has exactly one correct note. Real queries can have
  several relevant notes; this harness has no notion of graded or multi-gold relevance.
- **Query/gold lexical leakage is mitigated, not eliminated.** Because `query` is a source note's
  label and `flat` searches full note text (not just labels), some "multi-hop" golds are still
  reachable by flat through incidental text overlap the label-overlap filter doesn't catch —
  flat's non-zero 0.2889 hit@10 on multi-hop probes shows this directly. The overlap filter
  reduces this leakage; it does not remove it.
- **The reasoned-arm adjacency is one modeling choice, not the only one.** Entailed note-to-note
  edges are added at a uniform weight of 1.0 (entailed triples carry no confidence of their own),
  and `type_cohort` (linking notes that share an entailed `kl:` class) is off by default. A
  different weighting or a type-cohort-on run could change finding 3's margin, though it's
  unlikely to flip the direction given how close `reasoned` already tracks `graph`.
- **A single deterministic run, not a cross-validated benchmark.** Probe generation and metrics
  have no randomness, so a re-run reproduces these exact numbers — but there are no confidence
  intervals, no held-out split, and no statistical significance test. N (180 / 517) is reported;
  significance testing beyond that is out of scope by design (see the spec's non-goals).
- **The vault is the author's own** (~517 notes, a personal knowledge base). These results may
  not generalize to a different corpus, domain, or scale — larger or more densely interlinked
  vaults could show a different balance between graph lift and reasoning's marginal value.

## Reproduce

```
cd ~/graph-guard && source .venv/bin/activate && python -m eval.real_vault_lift
```

This reads the private vault (`rag_guard.config.default_roots()`) and writes
`eval/results.json` — aggregate-only (counts and metrics; no note ids, paths, filenames, or
query/gold text), enforced by a leak-check test in `tests/test_real_vault_lift.py`. The
committed `eval/results.json` in this repo is that file, unedited.

Prior art, no novelty claimed: [GraphRAG](https://arxiv.org/abs/2404.16130) (graph-structured
retrieval framing), [HippoRAG](https://arxiv.org/abs/2405.14831) (the Personalized-PageRank
mechanism the graph/reasoned arms implement),
[GraphRAG-Bench](https://arxiv.org/abs/2506.05690) (graphs win on multi-hop, not simple lookups —
matches findings 1 and 2 here, now on this project's own vault instead of a benchmark corpus),
and "Knowledge Conceptualization Impacts RAG Efficacy"
([arXiv:2507.09389](https://arxiv.org/abs/2507.09389)) (ontology right-sizing — matches finding
3's read that more formal semantics doesn't automatically buy more retrieval quality). See
`docs/TRADEOFFS.md` for the qualitative version of findings 1–2 and `docs/SPARQL-vs-PPR.md` for
the mechanism behind finding 3's "reasoning earns its cost elsewhere" conclusion.
