"""owlrl-materialized RDF graph -> note-id adjacency bridge (Gate D, Task 1).

Gate D's "reasoned" retrieval arm (A3) runs Personalized PageRank (`graph_guard.ppr`) over
the OWL-entailed graph instead of the raw KG, to see whether owlrl's entailments (the
`kl:supersedesTransitively` closure, `skos:broader` rollups, subclass typing, ...) lift
multi-hop retrieval beyond what the raw `TripleStore.adjacency()` graph arm (A2) already
gives PageRank. But `personalized_pagerank` only understands a note-id adjacency dict, and
`reasoning.materialize` only understands RDF/IRI space -- this module is the bridge: it
starts from the store's asserted adjacency, then folds in the entailed graph, returning a
`{note_id: {neighbor_id: weight}}` dict shaped exactly like `TripleStore.adjacency()`, so it
drops straight into `ppr.personalized_pagerank`.

**A3 = A2 + only-the-edges-reasoning-reveals.** So the arms differ ONLY by what reasoning
adds, never by re-weighting:
  - Start from a deep copy of `store.adjacency()` -- this carries every ASSERTED edge at its
    real confidence weight (the graph arm A2). Deep-copied so the store's structure is never
    mutated.
  - Then walk the materialized graph and add an entailed note<->note edge ONLY for a pair
    that is NOT already connected in that starting adjacency (`o_id in adj[s_id]` -> skip).
    That leaves every asserted edge at its original confidence and adds only genuinely-new
    reachability -- e.g. the transitive A->C/A->D supersedes closure -- at a uniform weight
    of 1.0. Uniform because entailed triples carry no confidence of their own (confidence
    lives only in `rdf_export`'s reification blocks, keyed to a specific ASSERTED triple, not
    to whatever an owlrl rule derives from it).

Projection rule for what counts as an entailed edge: a materialized triple `(s, p, o)`
becomes a candidate note<->note edge only when BOTH `s` and `o` resolve (`fuseki._iri_to_id`)
to real note ids already in the store, AND `p` is a relational `kl:`/`skos:` predicate --
never `rdf:type`, `schema:name`, or any triple in the reification vocabulary
(`rdf:Statement`/`rdf:subject`/`rdf:predicate`/`rdf:object`/`kl:confidence`/`kl:provenance`/
`kl:span`) that `rdf_export` emits alongside every asserted edge. That keeps entailed
*typing* (e.g. a `Project` note's entailed `rdf:type schema:Project`) and provenance
bookkeeping from ever leaking into the graph as a spurious note<->note edge.

`type_cohort=True` is an off-by-default experiment toggle: it additionally connects every
pair of notes that share an entailed **kl: entity class** (grouping note ids by their
`rdf:type kl:<Type>`). It deliberately ignores the universal types owlrl materializes on
every individual (`owl:Thing`, `rdfs:Resource`) and the external super-classes
(`schema:*`/`skos:*`) -- grouping by those would link every note to every other note (the
`owl:Thing` cohort) and make the toggle meaningless. Even restricted to kl: types this is a
much noisier signal than the relational edges above (two unrelated `Project` notes get
linked just for sharing a type), so it's kept opt-in for Gate D to measure separately rather
than baked into the default reasoned arm.
"""
from __future__ import annotations

import copy

from rdflib import RDF

from graph_guard import rdf_export, reasoning
from graph_guard.fuseki import _iri_to_id
from graph_guard.rdf_export import KL, SCHEMA, SKOS

# Predicates that must never become adjacency edges: RDF typing, the node's display
# name, and every predicate in the reification vocabulary rdf_export.store_to_graph
# emits per asserted edge (a `kl:stmt/<n> a rdf:Statement` block carrying
# rdf:subject/predicate/object + kl:confidence/provenance/span). None of these encode
# a note<->note relation, even after owlrl materialization.
_EXCLUDE_PREDICATES = frozenset({
    RDF.type,
    SCHEMA.name,
    RDF.subject,
    RDF.predicate,
    RDF.object,
    KL.confidence,
    KL.provenance,
    KL.span,
})

_RELATIONAL_NAMESPACES = (str(KL), str(SKOS))

_ENTAILED_EDGE_WEIGHT = 1.0


def _add_edge(adj: dict[str, dict[str, float]], a: str, b: str, weight: float) -> None:
    adj.setdefault(a, {})
    adj.setdefault(b, {})
    adj[a][b] = adj[a].get(b, 0.0) + weight
    adj[b][a] = adj[b].get(a, 0.0) + weight


def reasoned_adjacency(store, *, type_cohort: bool = False) -> dict[str, dict[str, float]]:
    """Return A3: the asserted graph-arm adjacency (`store.adjacency()`, at its real
    confidence weights) PLUS only the genuinely-new note<->note edges OWL reasoning reveals
    (weight 1.0). Same `{node_id: {neighbor_id: weight}}` shape `TripleStore.adjacency()`
    returns, so it's a drop-in for `ppr.personalized_pagerank`.

    Asserted edges keep their confidence untouched; an entailed edge is added only for a pair
    not already connected. See the module docstring for exactly what counts as an entailed
    edge vs. what's excluded (typing, reification), and why `type_cohort` is opt-in.
    """
    g = reasoning.materialize(rdf_export.store_to_graph(store))
    note_ids = {n["id"] for n in store.all_nodes()}

    # A2, at real confidence weights. Deep copy so the store's dict is never mutated; only
    # genuinely-new entailed edges are folded in on top.
    adj: dict[str, dict[str, float]] = copy.deepcopy(store.adjacency())

    for s, p, o in g:
        if p in _EXCLUDE_PREDICATES:
            continue
        if not str(p).startswith(_RELATIONAL_NAMESPACES):
            continue
        s_id = _iri_to_id(str(s))
        if s_id not in note_ids:
            continue
        o_id = _iri_to_id(str(o))
        if o_id not in note_ids:
            continue
        if o_id in adj.get(s_id, {}):
            continue  # already connected in A2 (or a prior entailed add) -> preserve its weight
        _add_edge(adj, s_id, o_id, _ENTAILED_EDGE_WEIGHT)

    if type_cohort:
        cohorts: dict[str, list[str]] = {}
        for s, _p, o in g.triples((None, RDF.type, None)):
            if not str(o).startswith(str(KL)):
                continue  # kl: entity classes only -- skip owl:Thing/rdfs:Resource/schema:/skos:
            s_id = _iri_to_id(str(s))
            if s_id not in note_ids:
                continue
            cohorts.setdefault(str(o), []).append(s_id)
        for members in cohorts.values():
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    _add_edge(adj, members[i], members[j], _ENTAILED_EDGE_WEIGHT)

    return adj
