from rdflib import RDF, Graph, Literal, URIRef
from rdflib.namespace import XSD

from graph_guard.rdf_export import KL, SCHEMA, export_turtle, node_iri, store_to_graph
from graph_guard.store import TripleStore


def _small_store():
    s = TripleStore()
    s.upsert_node({"id": "A", "type": "Project", "name": "Project A"})
    s.upsert_node({"id": "B", "type": "Project", "name": "Project B"})
    s.upsert_node({"id": "C", "type": "Person", "name": "Gina"})
    s.upsert_edge({"src": "A", "predicate": "supersedes", "dst": "B",
                    "note_path": "project_a.md", "confidence": 0.75,
                    "extractor": "frontmatter"})
    s.upsert_edge({"src": "C", "predicate": "mentions", "dst": "A"})
    return s


def test_round_trip_triple_count():
    s = _small_store()
    ttl = export_turtle(s)
    g = Graph().parse(data=ttl, format="turtle")

    assert (node_iri("A"), KL.supersedes, node_iri("B")) in g
    assert (node_iri("C"), KL.mentions, node_iri("A")) in g

    stmts = list(g.subjects(RDF.type, RDF.Statement))
    assert len(stmts) == 2


def test_known_spo_present():
    s = _small_store()
    g = store_to_graph(s)
    assert (node_iri("A"), KL.supersedes, node_iri("B")) in g


def test_provenance_carried_on_reification():
    s = _small_store()
    g = store_to_graph(s)

    match = None
    for stmt in g.subjects(RDF.type, RDF.Statement):
        if (stmt, RDF.subject, node_iri("A")) in g and (stmt, RDF.predicate, KL.supersedes) in g:
            match = stmt
            break
    assert match is not None

    confidence = g.value(match, KL.confidence)
    provenance = g.value(match, KL.provenance)
    assert confidence == Literal(0.75, datatype=XSD.decimal)
    assert str(provenance) == "project_a.md"


def test_reification_omits_missing_provenance_and_span():
    s = _small_store()
    g = store_to_graph(s)

    match = None
    for stmt in g.subjects(RDF.type, RDF.Statement):
        if (stmt, RDF.subject, node_iri("C")) in g and (stmt, RDF.predicate, KL.mentions) in g:
            match = stmt
            break
    assert match is not None
    assert g.value(match, KL.provenance) is None
    assert g.value(match, KL.span) is None


def test_reification_carries_span_when_present():
    s = TripleStore()
    s.upsert_node({"id": "A", "type": "Project", "name": "Project A"})
    s.upsert_node({"id": "B", "type": "Project", "name": "Project B"})
    s.upsert_edge({"src": "A", "predicate": "supersedes", "dst": "B",
                    "note_path": "project_a.md", "span": "L10-L12", "confidence": 0.75})
    g = store_to_graph(s)

    match = None
    for stmt in g.subjects(RDF.type, RDF.Statement):
        if (stmt, RDF.subject, node_iri("A")) in g:
            match = stmt
            break
    assert match is not None
    assert str(g.value(match, KL.span)) == "L10-L12"


def test_types_and_names_present():
    s = _small_store()
    g = store_to_graph(s)
    assert (node_iri("A"), RDF.type, KL.Project) in g
    assert (node_iri("A"), SCHEMA.name, Literal("Project A")) in g
    assert (node_iri("C"), RDF.type, KL.Person) in g


def test_node_iri_deterministic_same_id():
    assert node_iri("A") == node_iri("A")


def test_node_iri_handles_unsafe_chars():
    iri = node_iri("some path/with spaces.md")
    assert isinstance(iri, URIRef)
    # must round-trip through a real Turtle parse without exploding
    g = Graph()
    g.add((iri, RDF.type, KL.Note))
    ttl = g.serialize(format="turtle")
    g2 = Graph().parse(data=ttl, format="turtle")
    assert (iri, RDF.type, KL.Note) in g2


def test_empty_store_produces_valid_empty_turtle():
    s = TripleStore()
    ttl = export_turtle(s)
    g = Graph().parse(data=ttl, format="turtle")
    assert len(list(g.subjects(RDF.type, RDF.Statement))) == 0
    assert len(g) == 0


def test_export_turtle_writes_file_matching_return_value(tmp_path):
    s = _small_store()
    p = tmp_path / "kg.ttl"
    returned = export_turtle(s, path=str(p))
    assert p.exists()
    file_ttl = p.read_text()

    g_returned = Graph().parse(data=returned, format="turtle")
    g_file = Graph().parse(data=file_ttl, format="turtle")
    assert set(g_returned) == set(g_file)


def test_namespaces_bound_on_graph():
    s = _small_store()
    g = store_to_graph(s)
    prefixes = {p: str(ns) for p, ns in g.namespaces()}
    assert prefixes.get("kl") == "https://jott2121.github.io/graph-guard/ns#"
    assert prefixes.get("schema") == "https://schema.org/"
    assert prefixes.get("skos") == "http://www.w3.org/2004/02/skos/core#"
