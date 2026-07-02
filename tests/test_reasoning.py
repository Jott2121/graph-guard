from rdflib import RDF

from graph_guard.rdf_export import KL, SCHEMA, SKOS, node_iri, store_to_graph
from graph_guard.reasoning import materialize
from graph_guard.store import TripleStore


def _chain_store():
    """A -> B -> C -> D via three asserted kl:supersedes edges (no direct A-C/A-D/B-D edges)."""
    s = TripleStore()
    for node_id in ("A", "B", "C", "D"):
        s.upsert_node({"id": node_id, "type": "Project", "name": f"Project {node_id}"})
    s.upsert_edge({"src": "A", "predicate": "supersedes", "dst": "B"})
    s.upsert_edge({"src": "B", "predicate": "supersedes", "dst": "C"})
    s.upsert_edge({"src": "C", "predicate": "supersedes", "dst": "D"})
    return s


def test_transitive_supersedes_entailed():
    s = _chain_store()
    data = store_to_graph(s)

    # Not asserted before materialization -- only single-hop edges exist in the raw export.
    assert (node_iri("A"), KL.supersedesTransitively, node_iri("D")) not in data

    m = materialize(data)

    # Entailed via kl:supersedes rdfs:subPropertyOf kl:supersedesTransitively (prp-spo1)
    # + kl:supersedesTransitively a owl:TransitiveProperty (prp-trp): the full closure
    # over the A->B->C->D chain, including the multi-hop A->D pair that is derivable
    # ONLY by inference (never asserted anywhere in the instance data).
    assert (node_iri("A"), KL.supersedesTransitively, node_iri("D")) in m
    assert (node_iri("A"), KL.supersedesTransitively, node_iri("C")) in m


def test_direct_supersedes_stays_single_hop():
    s = _chain_store()
    m = materialize(store_to_graph(s))

    # kl:supersedes is owl:FunctionalProperty and NOT owl:TransitiveProperty (Task 2's
    # DL-safe split), so it must NOT pick up the multi-hop closure -- only the separate
    # kl:supersedesTransitively super-property does.
    assert (node_iri("A"), KL.supersedes, node_iri("C")) not in m
    assert (node_iri("A"), KL.supersedes, node_iri("D")) not in m


def test_subclass_inheritance_entailed():
    s = TripleStore()
    s.upsert_node({"id": "X", "type": "Project", "name": "Project X"})
    data = store_to_graph(s)

    assert (node_iri("X"), RDF.type, SCHEMA.Project) not in data

    m = materialize(data)

    # Entailed via kl:Project rdfs:subClassOf schema:Project (cax-sco).
    assert (node_iri("X"), RDF.type, SCHEMA.Project) in m


def test_kl_broader_entails_skos_broader():
    s = TripleStore()
    s.upsert_node({"id": "X", "type": "Concept", "name": "Concept X"})
    s.upsert_node({"id": "Y", "type": "Concept", "name": "Concept Y"})
    s.upsert_edge({"src": "X", "predicate": "broader", "dst": "Y"})
    data = store_to_graph(s)

    assert (node_iri("X"), SKOS.broader, node_iri("Y")) not in data

    m = materialize(data)

    # Entailed via kl:broader rdfs:subPropertyOf skos:broader (prp-spo1).
    assert (node_iri("X"), SKOS.broader, node_iri("Y")) in m


def test_materialize_does_not_mutate_input():
    s = _chain_store()
    data = store_to_graph(s)
    before = len(data)

    materialize(data)

    assert len(data) == before


def test_materialize_without_ontology_skips_entailment():
    """with_ontology=False reasons over the data alone -- no T-Box, no entailment."""
    s = _chain_store()
    m = materialize(store_to_graph(s), with_ontology=False)

    assert (node_iri("A"), KL.supersedesTransitively, node_iri("D")) not in m
