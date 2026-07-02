# graph-guard — Gate D: real-vault retrieval-lift eval harness — spec

**Date:** 2026-07-02 · **Status:** spec (design approved by Jeff; not built) · **Branch:** `feat/gate-d-eval`
(off `feat/tier-b`). **Delivery:** Sonnet 5 implements test-first; Opus judges each diff + a whole-branch
review (same rhythm as Tier A/B). No new dependencies — reuses `rag_guard`, `rdflib`, `owlrl` already present.

## Why Gate D exists
Tier A and Tier B both ship an honest caveat: *"eval proves the mechanism, not real-vault lift
(unquantified)."* The existing `eval/eval_multihop.py` is a 2-node hand-built store with a hardcoded
`tfidf` stub — it proves graph retrieval CAN beat flat on a synthetic multi-hop case, but says nothing
about Jeff's real ~686-node vault. Gate D replaces that gap with **measured numbers**: does the typed-graph
layer (and its owlrl-reasoned extension) actually improve retrieval over flat lexical on the real vault?
This is the gate before any thought of wiring the ontology into live Bow, and the strongest Gina/Lockheed
artifact — either "here's measured lift," or the sharper honest result "at 686 notes heavyweight semantics
don't earn their retrieval cost; here's the scale where they would."

**Standard (non-negotiable, from rag-guard norms):** every printed metric comes from a real harness run;
nothing hardcoded. Committed output is aggregate-only — no private note paths/filenames (leak-check).

## Decisions locked (from the approved design)
- **Ground truth = structure-derived probes**, zero manual labeling. Two families (below).
- **3 arms:** A1 flat TF-IDF · A2 Tier-A graph (PPR+RRF) · A3 Tier-B owlrl-**reasoned** graph (PPR+RRF over
  the entailment-materialized adjacency).
- **PII:** committed `eval/results.json` + `docs/EVAL-real-vault-lift.md` carry **aggregate metrics only**
  (hit@k / MRR / N / lift). NEVER note ids, paths, filenames, or query/gold text. Any per-probe detail is
  local + gitignored. A test asserts results.json is path-free (leak-check as a test).
- **A3 reasoned adjacency default = entailed note→note edges only.** External-class type-typing
  (`schema:Project`) and type-cohort hubs are OFF by default (documented toggle) so A3 isn't just type-noise.
- **Real-vault run is a manual entry point**; CI tests run on synthetic fixtures only (CI never touches the
  private vault). Coverage ≥90% on new stdlib/pure code.

## The three arms (all in note-id space so results compare fairly)
- **A1 Flat** = `rag_guard.retriever.Retriever` TF-IDF over the real `.md` files (the pure-lexical `tfidf_fn`).
- **A2 Graph** = `graph_guard.graph_retriever.GraphRetriever.retrieve` = Personalized PageRank over the real
  KG adjacency (`TripleStore.adjacency()`), RRF-fused with A1. The Tier A working core, unchanged.
- **A3 Reasoned** = the SAME `GraphRetriever` logic but with PPR run over the **owlrl-materialized**
  adjacency (transitive-supersedes closure + any entailed note→note relations). Isolates the question:
  *does reasoning add retrieval value beyond raw PPR?*

## Components / tasks (each TDD, Opus-reviewed)

1. **`graph_guard/reasoned_graph.py`** — the owlrl-RDF → note-id-adjacency bridge.
   - `reasoned_adjacency(store, *, type_cohort=False) -> dict[str, dict[str, float]]`:
     `rdf_export.store_to_graph(store)` → `reasoning.materialize(graph)` → iterate materialized triples;
     for each `(s, p, o)` where s and o are BOTH `kl:n/` node IRIs (real notes, mapped back via
     `fuseki._iri_to_id`) and p is a `kl:` relational predicate (EXCLUDE `rdf:type`, `schema:name`, and the
     `rdf:Statement`/`rdf:subject|predicate|object`/`kl:confidence|provenance|span` reification vocabulary),
     add a symmetric weighted edge (default weight 1.0 for entailed edges) — same shape as
     `TripleStore.adjacency()`. When `type_cohort=True`, additionally connect notes sharing an entailed
     `rdf:type` via that type (documented; OFF by default).
   - Must return the SAME dict shape `personalized_pagerank` consumes.
   - Tests: fixture KG A→B→C via `supersedes`; assert the reasoned adjacency contains the entailed A–C edge
     that raw `store.adjacency()` does NOT; assert type-typing edges to external classes are excluded;
     assert symmetry; assert `type_cohort=True` adds the cohort edges and default omits them.

2. **Injectable adjacency on `GraphRetriever`** (minimal, backward-compatible edit to
   `graph_guard/graph_retriever.py`). Add an optional `adjacency_fn=None` constructor param; when None,
   default to `self._store.adjacency` (current behavior — Tier A tests must stay green). A3 is then just
   `GraphRetriever(store, tfidf_fn=..., text_for=..., adjacency_fn=lambda: reasoned_adjacency(store))`.
   This reuses ALL the PPR+RRF+specificity+hybrid logic instead of duplicating it.
   - Tests: existing Tier A `test_graph_retriever` still passes (default path unchanged); a new test shows
     injecting a custom adjacency changes the ranking as expected.

3. **`graph_guard/eval_probes.py`** — deterministic structure-derived probe generator.
   - `RELATIONAL = PREDICATES - {"mentions"}` (mentions is too generic; documented — make the excluded set
     an explicit constant, not a magic inline).
   - `multi_hop_probes(store, *, max_overlap=1) -> list[Probe]`: for each edge `(src, pred, dst)` with
     `pred in RELATIONAL` and both endpoints real notes, build `query = clean label of src`
     (reuse `graph_retriever._clean_label`), `gold = dst`. KEEP the probe only if the lexical overlap
     between the query tokens and dst's clean-label/text tokens is `<= max_overlap` (the low-overlap filter —
     this is what makes it a genuine multi-hop test flat can't win by lexical accident). Count and report
     discarded probes (never silently drop).
   - `simple_lookup_probes(store, *, n=None) -> list[Probe]`: for a DETERMINISTIC sample of notes
     (sorted by id, first `n` or all real notes), `query = that note's clean label`
     (`graph_retriever._clean_label`), `gold = that same note`. High query/gold overlap by construction —
     the easy-lookup control where the graph must NOT hurt. (Clean label chosen for determinism and
     consistency with the multi-hop family; no RNG, no per-note TF-IDF term extraction.)
   - `Probe` = a small dataclass/dict `{family, query, gold_id}`. Generation MUST be deterministic (no RNG).
   - Tests: fixture KG → multi-hop probes have `gold == dst` and pass the overlap filter; a high-overlap
     src/dst pair is discarded (counted); simple-lookup gold == self; determinism (two runs identical).

4. **`graph_guard/eval_metrics.py`** — ranking metrics.
   - `evaluate(arm_fn, probes, k=10) -> dict`: for each probe, `ranked_ids = [h["id"] for h in arm_fn(query, k)]`;
     `rank = index of gold_id + 1` (or None if absent in top-k). Aggregate `hit@1/@5/@10 = mean(gold in top-N)`
     and `MRR = mean(1/rank or 0)`. Return per-family and overall.
   - `lift(arm_metrics, baseline_metrics) -> dict`: absolute deltas per metric.
   - Tests: hand-built rankings with gold at a known rank → assert exact hit@k / MRR (e.g. gold at rank 3 →
     hit@1=0, hit@5=1, hit@10=1, RR=1/3); empty/absent-gold cases.

5. **`eval/real_vault_lift.py`** — the harness (manual entry point, not a CI test).
   - `run(roots=None, *, k=10, max_multihop=None, max_simple=None) -> dict`: build the SHARED pieces ONCE,
     mirroring `service.build_retriever`'s internals (do NOT call `build_retriever` — it only returns the
     fused A2 and hides the raw `tfidf_fn` the flat arm needs): build the real KG `store`
     (`extract.build_graph` over `config.default_roots()`), the `docs`/`text_map` from `extract._walk_md`,
     and `tfidf = rag_guard.retriever.Retriever(docs)`. Then construct the three arms as `(query,k)->hits`
     callables from those shared pieces: **A1** = `lambda q,k: tfidf.retrieve(q,k)`; **A2** =
     `GraphRetriever(store, tfidf_fn=A1, text_for=text_map.get)`; **A3** = the same but
     `adjacency_fn=lambda: reasoned_adjacency(store)`. Generate both probe families once. Evaluate all three
     arms. Assemble an **aggregate-only** result dict:
     `{vault:{nodes,edges}, probes:{multihop,simple,discarded}, arms:{flat,graph,reasoned:{multihop,simple,overall:{hit@1,hit@5,hit@10,mrr}}}, lift:{graph_vs_flat,reasoned_vs_flat,reasoned_vs_graph}}`.
     Build the three arms by reusing `service.build_retriever` where possible (DRY).
   - Writes `eval/results.json` (aggregate-only) and prints a labeled comparison table. Caps (`max_*`), if
     set, are LOGGED in the output (`probes.capped: true/false`) — no silent truncation.
   - `__main__`: `python -m eval.real_vault_lift` (default roots). Document that it reads the private vault
     and that its committed output is sanitized.
   - Tests (CI, synthetic fixture — NOT the real vault): build a small temp-dir vault of `.md` files with a
     known multi-hop structure (a note that supersedes/relates to a lexically-dissimilar note); run `run()`
     over it; assert the result dict has the expected keys/shape, that `graph`/`reasoned` arms find the
     multi-hop gold that `flat` misses on at least the constructed case, and that the harness completes.
   - **Leak-check test:** serialize `results.json` and assert it contains NO filesystem path (`/`, `.md`),
     NO note id, and NO query/gold text — aggregate numbers only.

6. **`docs/EVAL-real-vault-lift.md`** — the writeup (methodology + REAL numbers after a real run + honest
   limits). Structure: the question; the three arms; probe methodology (both families + the low-overlap
   filter); the REAL results table (pasted from an actual `python -m eval.real_vault_lift` run, aggregate
   only); interpretation (did the graph lift? did reasoning add anything beyond PPR?); and honest limits:
   structural probes measure multi-hop link-recovery + no-harm, NOT organic-question relevance; single-gold
   assumption; query/gold lexical-leakage mitigated-not-eliminated; the A3 adjacency-mapping is one design
   choice; no human relevance validation. Cite the same prior art (GraphRAG / HippoRAG / GraphRAG-Bench
   2506.05690 / arXiv 2507.09389). If the measured result is "no lift," report it straight.

## Runtime / correctness notes
- Build the three retrievers ONCE and reuse across all probes (do NOT rebuild TF-IDF/PPR/owlrl per probe).
- owlrl materialization runs once over the whole real KG — confirm it completes in reasonable time at 686
  nodes; if it's slow, materialize once and cache the reasoned adjacency for the run.
- Determinism: probe generation and metric computation have no RNG; a re-run yields identical aggregates
  (timings aside).

## Deps & non-goals
- **No new dependencies.** Reuses `rag_guard`, `rdflib`, `owlrl`, stdlib.
- **Non-goals (YAGNI):** LLM-as-judge relevance, hand-labeled gold sets, wiring into live Bow, web UI,
  graded/multi-gold relevance, statistical significance testing beyond reporting N. These are explicitly out.

## Resume checklist for a fresh session
- Repo `~/graph-guard`, branch `feat/gate-d-eval` (off `feat/tier-b`). Isolated `.venv` (uv, py3.14) already
  has everything. Test cmd: `cd ~/graph-guard && . .venv/bin/activate && python -m pytest -q --cov=graph_guard`.
- Reuse read-only: `graph_retriever` (add the `adjacency_fn` param — task 2), `ppr`, `store`, `extract`,
  `service.build_retriever`, `rdf_export`, `reasoning.materialize`, `fuseki._iri_to_id`, `schema.PREDICATES`,
  `rag_guard.retriever.Retriever`, `rag_guard.config.default_roots`.
- Rhythm: Sonnet builds each task test-first; Opus reviews each diff + a whole-branch review; ledger at
  `.superpowers/sdd/progress.md`; ≥90% coverage on new code; real-vault run is manual + sanitized output.
