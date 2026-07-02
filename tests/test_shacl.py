from rdflib import RDF, Graph, Literal, Namespace

from graph_guard.rdf_export import KL, SCHEMA, node_iri, store_to_graph
from graph_guard.schema import ENTITY_TYPES, FUNCTIONAL
from graph_guard.shacl import load_shapes, validate
from graph_guard.store import TripleStore

SH = Namespace("http://www.w3.org/ns/shacl#")


def _valid_store():
    """2-3 typed, named nodes; each functional predicate used at most once per node."""
    s = TripleStore()
    s.upsert_node({"id": "A", "type": "Project", "name": "Project A"})
    s.upsert_node({"id": "B", "type": "Project", "name": "Project B"})
    s.upsert_node({"id": "C", "type": "Person", "name": "Gina"})
    s.upsert_edge({"src": "A", "predicate": "supersedes", "dst": "B",
                    "note_path": "project_a.md", "confidence": 0.75,
                    "extractor": "frontmatter"})
    s.upsert_edge({"src": "C", "predicate": "mentions", "dst": "A"})
    return s


def test_shapes_parse():
    g = load_shapes()
    assert isinstance(g, Graph)
    assert len(g) > 0


def test_valid_graph_conforms():
    conforms, results_graph, results_text = validate(store_to_graph(_valid_store()))
    assert conforms is True


def test_missing_name_fails():
    g = store_to_graph(_valid_store())
    g.add((node_iri("X"), RDF.type, KL.Project))
    conforms, results_graph, results_text = validate(g)
    assert conforms is False
    assert "name" in results_text.lower() or "minCount" in results_text or "MinCount" in results_text


def test_missing_type_fails():
    g = store_to_graph(_valid_store())
    g.add((node_iri("Y"), SCHEMA.name, Literal("Untyped thing")))
    conforms, results_graph, results_text = validate(g)
    assert conforms is False


def test_double_supersedes_fails():
    g = store_to_graph(_valid_store())
    s = TripleStore()
    s.upsert_node({"id": "D", "type": "Project", "name": "Project D"})
    s.upsert_node({"id": "E", "type": "Project", "name": "Project E"})
    s.upsert_node({"id": "F", "type": "Project", "name": "Project F"})
    extra = store_to_graph(s)
    for triple in extra:
        g.add(triple)
    g.add((node_iri("D"), KL.supersedes, node_iri("E")))
    g.add((node_iri("D"), KL.supersedes, node_iri("F")))
    conforms, results_graph, results_text = validate(g)
    assert conforms is False


def test_double_has_status_fails():
    g = store_to_graph(_valid_store())
    s = TripleStore()
    s.upsert_node({"id": "G", "type": "Project", "name": "Project G"})
    s.upsert_node({"id": "H", "type": "Concept", "name": "Status H"})
    s.upsert_node({"id": "I", "type": "Concept", "name": "Status I"})
    extra = store_to_graph(s)
    for triple in extra:
        g.add(triple)
    g.add((node_iri("G"), KL.has_status, node_iri("H")))
    g.add((node_iri("G"), KL.has_status, node_iri("I")))
    conforms, results_graph, results_text = validate(g)
    assert conforms is False


def test_reification_statements_not_falsely_flagged():
    conforms, results_graph, results_text = validate(store_to_graph(_valid_store()))
    assert conforms is True


def test_typed_instance_shape_targets_every_entity_type():
    """Anti-drift pin (ontology/shapes.ttl header comment): kl:TypedInstanceShape's
    sh:targetClass list must cover every name in graph_guard.schema.ENTITY_TYPES.
    Without this, adding a 12th entity type to schema.py could silently leave
    shapes.ttl out of date -- a new typed-but-unnamed node would wrongly pass S2
    validation because no sh:targetClass would ever target it."""
    g = load_shapes()
    for t in ENTITY_TYPES:
        assert (KL.TypedInstanceShape, SH.targetClass, KL[t]) in g, (
            f"schema.ENTITY_TYPES has {t!r} but kl:TypedInstanceShape has no "
            f"matching sh:targetClass in ontology/shapes.ttl"
        )


def test_entity_shape_caps_every_functional_predicate_at_one():
    """Anti-drift pin (ontology/shapes.ttl header comment): kl:EntityShape must carry
    an S3 property shape (sh:maxCount 1) for every predicate in
    graph_guard.schema.FUNCTIONAL. Without this, adding a new functional predicate to
    schema.py could silently leave shapes.ttl out of date -- a node with two values for
    the new predicate would wrongly pass validation."""
    g = load_shapes()
    for f in FUNCTIONAL:
        assert any(
            (blank, SH.path, KL[f]) in g and (blank, SH.maxCount, Literal(1)) in g
            for blank in g.objects(KL.EntityShape, SH.property)
        ), (
            f"schema.FUNCTIONAL has {f!r} but kl:EntityShape has no sh:property shape "
            f"with sh:path kl:{f} and sh:maxCount 1 in ontology/shapes.ttl"
        )
