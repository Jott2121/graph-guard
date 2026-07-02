import owlrl
from rdflib import Graph
from rdflib.namespace import OWL, RDF, RDFS

from graph_guard.ontology import load_ontology
from graph_guard.rdf_export import KL, SCHEMA, SKOS
from graph_guard.schema import ENTITY_TYPES, FUNCTIONAL, PREDICATES


def test_ontology_parses():
    g = load_ontology()
    assert isinstance(g, Graph)
    assert len(g) > 0


def test_every_entity_type_is_owl_class():
    g = load_ontology()
    for t in ENTITY_TYPES:
        assert (KL[t], RDF.type, OWL.Class) in g, f"{t} not declared owl:Class"


def test_every_predicate_is_object_property():
    g = load_ontology()
    for p in PREDICATES:
        assert (KL[p], RDF.type, OWL.ObjectProperty) in g, f"{p} not declared owl:ObjectProperty"


def test_functional_predicates_declared():
    g = load_ontology()
    for f in FUNCTIONAL:
        assert (KL[f], RDF.type, OWL.FunctionalProperty) in g, f"{f} not declared owl:FunctionalProperty"


def test_supersedes_split_is_dl_safe():
    g = load_ontology()
    assert (KL.supersedesTransitively, RDF.type, OWL.TransitiveProperty) in g
    assert (KL.supersedes, RDFS.subPropertyOf, KL.supersedesTransitively) in g
    assert (KL.supersedes, RDF.type, OWL.TransitiveProperty) not in g


def test_required_subclass_axioms():
    g = load_ontology()
    assert (KL.Person, RDFS.subClassOf, SCHEMA.Person) in g
    assert (KL.Project, RDFS.subClassOf, SCHEMA.Project) in g
    assert (KL.Event, RDFS.subClassOf, SCHEMA.Event) in g
    assert (KL.Claim, RDFS.subClassOf, SCHEMA.Claim) in g
    assert (KL.Concept, RDFS.subClassOf, SKOS.Concept) in g


def test_skos_bridge():
    g = load_ontology()
    assert (KL.broader, RDFS.subPropertyOf, SKOS.broader) in g
    assert (KL.narrower, RDFS.subPropertyOf, SKOS.narrower) in g


def test_authored_created_range_person():
    g = load_ontology()
    assert (KL.authored_by, RDFS.range, KL.Person) in g
    assert (KL.created_by, RDFS.range, KL.Person) in g


def test_owlrl_materializes_without_error():
    g = load_ontology()
    before = len(g)
    owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(g)
    assert len(g) > before
