"""OWL reasoning / entailment demo over the exported RDF instance data (Tier B, Task 5).

The payoff of modeling the graph as a formal OWL ontology (Task 2) instead of a plain
labeled-property graph: facts can be **entailed**, not just retrieved. `graph_guard.rdf_export`
asserts only single-hop, literal triples (e.g. one `kl:supersedes` edge per note, `rdf:type
kl:<Type>` directly) -- it never writes `kl:supersedesTransitively`, `schema:Project`, or
`skos:broader` triples itself. Those only appear after `materialize()` combines the instance
data with the OWL T-Box (`graph_guard.ontology.load_ontology`) and runs an OWL 2 RL reasoner
(`owlrl`) over the union.

Why the ontology must be in the mix: the T-Box axioms that drive entailment --
`kl:supersedes rdfs:subPropertyOf kl:supersedesTransitively` +
`kl:supersedesTransitively a owl:TransitiveProperty`, `kl:broader rdfs:subPropertyOf
skos:broader`, and `kl:Project rdfs:subClassOf schema:Project` -- live in
`graph_guard/ontology_data/ontology.ttl`,
not in the instance data. Reasoning over the data alone (`with_ontology=False`) has no axioms to
apply and entails nothing beyond what's already asserted. owlrl never fetches external
vocabularies over the network either way; `schema:Project`/`skos:Concept` etc. are only "known"
because the ontology graph itself names them in a `rdfs:subClassOf`/`subPropertyOf` triple.

`owlrl.OWLRL_Semantics` (OWL 2 RL, a decidable rule-based fragment of OWL 2) supplies the three
rules exercised by the tests below:
  - **prp-trp** (transitive property): if `p` is `owl:TransitiveProperty` and `x p y`, `y p z`
    then `x p z`. Fires on `kl:supersedesTransitively` to build the full multi-hop closure.
  - **prp-spo1** (sub-property): if `p1 rdfs:subPropertyOf p2` and `x p1 y` then `x p2 y`.
    Fires twice: `kl:supersedes` -> `kl:supersedesTransitively` (feeding prp-trp above) and
    `kl:broader` -> `skos:broader`.
  - **cax-sco** (class subsumption): if `c1 rdfs:subClassOf c2` and `x a c1` then `x a c2`.
    Fires on `kl:Project rdfs:subClassOf schema:Project` to entail the schema.org typing.

Because `kl:supersedes` is `owl:FunctionalProperty` but deliberately NOT `owl:TransitiveProperty`
(Task 2's DL-safe split -- OWL 2 DL forbids a property being both), prp-trp never touches
`kl:supersedes` itself: the multi-hop closure lands only on the separate
`kl:supersedesTransitively` super-property, while `kl:supersedes` stays single-hop/asserted-only
for Task 4's SPARQL property-path walk. This module's tests are the proof that split works.
"""
from __future__ import annotations

import owlrl
from rdflib import Graph

from graph_guard.ontology import load_ontology


def materialize(data_graph: Graph, *, with_ontology: bool = True) -> Graph:
    """Return a NEW graph = `data_graph` (+ the OWL T-Box, unless `with_ontology=False`) with
    owlrl's OWL 2 RL inferences materialized (`owlrl.DeductiveClosure(owlrl.OWLRL_Semantics)`).

    Does not mutate `data_graph`: all triples are copied into a fresh `rdflib.Graph` before
    the reasoner expands it in place, so the caller's original graph is left exactly as-is.
    """
    g = Graph()
    for triple in data_graph:
        g.add(triple)
    if with_ontology:
        for triple in load_ontology():
            g.add(triple)

    owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(g)
    return g
