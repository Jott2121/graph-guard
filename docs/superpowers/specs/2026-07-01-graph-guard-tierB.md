# graph-guard — Tier B (RDF/OWL/SHACL + SPARQL enterprise-fidelity layer) — spec

**Date:** 2026-07-01 · **Status:** spec (approved direction; not built) · written while the RDF/OWL/AWS
research was warm so a fresh session can execute without re-researching.
**Delivery:** Sonnet 5 implements test-first; Opus judges (same model as Tier A). New deps live in
the `[rdf]` extra — Tier A stays near-stdlib.

## Why Tier B exists
Tier A (built: SQLite triples + PageRank, 51 tests, live over the vault) is the pragmatic working
core. Tier B is the deliberate **enterprise-fidelity** layer: model the same graph as a formal
ontology (RDF/OWL/SHACL), serve it over **SPARQL** on a local triplestore, and demonstrate
**reasoning/entailment**. Purpose: (1) genuine hands-on with the exact stack Jeff would build at
Lockheed under Gina (AWS Neptune uses RDF/SPARQL + external reasoners); (2) the architect artifact —
run the *same* query as SPARQL vs PageRank and show **when the heavyweight semantic stack earns its
cost**. Right-sizing note (arXiv 2507.09389): keep OWL expressive enough to be useful, not maximal.

## Decisions carried from Tier A design
- **Local-first** triplestore: **Apache Jena Fuseki** (RDF/SPARQL, Java) — free, fast to stand up,
  same skills as Neptune's RDF side. AWS Neptune = documented *mirror path*, NOT built.
- RDF/Turtle is an **export/interop** format serialized FROM the SQLite triples (Tier A stays the
  live retrieval engine). Do not make SPARQL the live retrieval path.

## Components / tasks (each TDD, Opus-reviewed)
1. **`graph_guard/rdf_export.py`** — serialize the SQLite store → RDF/Turtle. Namespaces:
   `schema:` (schema.org), `skos:`, and a minted `kl:` (`https://jott2121.github.io/graph-guard/ns#`).
   Map entity types → `owl:Class` instances; predicates → `owl:ObjectProperty` (mentions/about/…);
   carry **provenance + confidence** per statement via **RDF reification** (or RDF-star if the chosen
   rdflib supports it) — decide and document. Tests: parse the emitted Turtle with `rdflib`, assert
   round-trip triple counts + a few known (s,p,o).
2. **`ontology/ontology.ttl`** — the OWL schema: `owl:Class` for each entity type with
   `rdfs:subClassOf` (e.g. `kl:Project rdfs:subClassOf schema:Project`), `owl:ObjectProperty` with
   `rdfs:domain`/`rdfs:range`, and `owl:FunctionalProperty` for `kl:has_status`/`kl:supersedes`
   (mirrors Tier A's FUNCTIONAL set → contradiction). Test: `rdflib` loads it; SHACL/owl sanity.
3. **`ontology/shapes.ttl`** — SHACL shapes validating instance data (node has a type; required
   `name`; functional-predicate max-count 1). Task: run `pyshacl` over exported data; a deliberately
   bad graph fails validation (test).
4. **`graph_guard/fuseki.py` + `scripts/run-fuseki.sh`** — load the Turtle into a local Fuseki
   dataset and expose SPARQL. Provide `sparql(query) -> rows` (via `rdflib` SPARQLWrapper or HTTP).
   Ship **example queries**: multi-hop via property path (`kl:supersedes+`), type-filtered retrieval,
   thematic rollups via SKOS `skos:broader`. (Fuseki needs Java — document install; gate the
   live-endpoint tests behind an env flag so CI stays green without a server.)
5. **Reasoning/entailment demo** — `owlrl` (or Jena's reasoner) materializes inferred triples
   (transitive `supersedes`, subclass inheritance) so answers are **entailed, not just retrieved**.
   Test: a fact derivable only by inference is returned post-materialization.
6. **`docs/SPARQL-vs-PPR.md`** — the architect writeup: same "what superseded X, transitively?"
   answered by (a) Tier-A PageRank and (b) a Tier-B SPARQL property-path over the reasoned graph;
   compare precision, explainability, cost, latency. This is the Gina/Lockheed demo.

## Deps (all in `[rdf]` extra)
`rdflib>=7`, `pyshacl` (SHACL), `owlrl` (reasoning). Apache Jena Fuseki (external, Java) for the
live SPARQL server — document download; keep server-dependent tests opt-in.

## Non-goals (Tier B)
- AWS Neptune / cloud (documented mirror only). No production deployment. No change to Tier A's live
  retrieval path (SPARQL is the fidelity/interop + demo layer, not the daily driver).

## Resume checklist for the fresh session
- Repo `~/graph-guard`, branch `feat/tier-a` (Tier A merged-or-not per Jeff). Create `feat/tier-b`.
- Tier A modules to reuse: `store.TripleStore` (source of triples), `schema` (types/predicates/
  FUNCTIONAL → OWL classes/properties/FunctionalProperty). Read them first.
- Follow the Tier-A rhythm: Sonnet builds each task test-first; Opus reviews each diff + a
  whole-branch review; ledger at `.superpowers/sdd/progress.md`; ≥90% coverage on new stdlib-testable
  code (exclude the Java-Fuseki live path behind an env flag).
