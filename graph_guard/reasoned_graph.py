"""owlrl-materialized RDF graph -> note-id adjacency bridge (Gate D, Task 1).

Gate D's "reasoned" retrieval arm runs Personalized PageRank (`graph_guard.ppr`) over
the OWL-entailed graph instead of the raw KG, to see whether owlrl's entailments (the
`kl:supersedesTransitively` closure, `skos:broader` rollups, subclass typing, ...) lift
multi-hop retrieval beyond what `TripleStore.adjacency()` already gives PageRank. But
`personalized_pagerank` only understands a note-id adjacency dict, and `reasoning.materialize`
only understands RDF/IRI space -- this module is the bridge between the two: it
materializes the store's KG, then projects the entailed graph back into a
`{note_id: {neighbor_id: weight}}` dict shaped exactly like `TripleStore.adjacency()`,
so it drops straight into `ppr.personalized_pagerank`.

Projection rule: a materialized triple `(s, p, o)` becomes a note<->note adjacency edge
only when BOTH `s` and `o` resolve (`fuseki._iri_to_id`) to real note ids already in the
store, AND `p` is a relational `kl:`/`skos:` predicate -- never `rdf:type`, `schema:name`,
or any triple in the reification vocabulary (`rdf:Statement`/`rdf:subject`/`rdf:predicate`/
`rdf:object`/`kl:confidence`/`kl:provenance`/`kl:span`) that `rdf_export` emits alongside
every asserted edge to carry provenance/confidence. That keeps entailed *typing* (e.g. a
`Project` note's entailed `rdf:type schema:Project`) and provenance bookkeeping from ever
leaking into the graph as a spurious note<->note edge, while still surfacing genuinely new
entailed note<->note edges like the supersedes-transitive closure.

Every edge here -- asserted or entailed alike -- gets a uniform weight of 1.0: the
materialized graph carries no confidence for entailed triples (confidence lives only in
`rdf_export`'s reification blocks, keyed to a specific asserted triple, not to whatever an
owlrl rule derives from it), so a uniform weight is used rather than trying to selectively
recover confidence for the subset of edges that happen to be directly asserted. Weights
accumulate the same way `TripleStore.adjacency()`'s do if a pair collapses onto the same
edge more than once (e.g. via `type_cohort` below).

`type_cohort=True` is an off-by-default experiment toggle: it additionally connects every
pair of notes that share an entailed `rdf:type` (grouping note ids by
`rdf:type kl:<Type>`/`schema:*`/`skos:*`). This is a much noisier signal than the relational
edges above (two unrelated `Project` notes get linked just for sharing a type) -- kept
opt-in so Gate D can measure it as a separate experiment rather than baking it into the
default reasoned arm.
"""
from __future__ import annotations

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

_EDGE_WEIGHT = 1.0


def _add_edge(adj: dict[str, dict[str, float]], a: str, b: str, weight: float = _EDGE_WEIGHT) -> None:
    adj.setdefault(a, {})
    adj.setdefault(b, {})
    adj[a][b] = adj[a].get(b, 0.0) + weight
    adj[b][a] = adj[b].get(a, 0.0) + weight


def reasoned_adjacency(store, *, type_cohort: bool = False) -> dict[str, dict[str, float]]:
    """Materialize `store`'s KG (`reasoning.materialize` over `rdf_export.store_to_graph`)
    and project it back into a symmetric, weighted note-id adjacency dict -- the same
    `{node_id: {neighbor_id: weight}}` shape `TripleStore.adjacency()` returns, so it's a
    drop-in for `ppr.personalized_pagerank`.

    Unlike the raw store adjacency, this includes entailed note<->note edges (e.g. the
    transitive-supersedes closure) that only exist after OWL reasoning. See the module
    docstring for exactly what counts as an edge vs. what's excluded (typing, reification).

    `type_cohort=False` by default -- see the module docstring for why it's opt-in.
    """
    g = reasoning.materialize(rdf_export.store_to_graph(store))
    note_ids = {n["id"] for n in store.all_nodes()}

    adj: dict[str, dict[str, float]] = {}

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
        _add_edge(adj, s_id, o_id)

    if type_cohort:
        cohorts: dict[str, list[str]] = {}
        for s, _p, o in g.triples((None, RDF.type, None)):
            s_id = _iri_to_id(str(s))
            if s_id not in note_ids:
                continue
            cohorts.setdefault(str(o), []).append(s_id)
        for members in cohorts.values():
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    _add_edge(adj, members[i], members[j])

    return adj
