"""SQLite triple store -> RDF/Turtle export (Tier B, foundation layer).

Turns Tier A's live `TripleStore` (graph_guard/store.py) into a formal RDF graph that
later Tier B tasks validate (SHACL), reason over (owlrl) and query (SPARQL). Tier A stays
the live retrieval engine; this module is a read-only, pure export/interop layer -- it
never mutates the store.

Namespaces (D2):
  kl:     https://jott2121.github.io/graph-guard/ns#   (this project's vocabulary)
  schema: https://schema.org/
  skos:   http://www.w3.org/2004/02/skos/core#
  plus rdflib's built-in rdf, rdfs, owl, xsd.

IRI minting (D2):
  - node IRI:      kl:n/<slug>  where <slug> is a URL-safe, deterministic transform of the
                    node id (non `[A-Za-z0-9_-]` bytes percent-encoded via urllib.parse.quote,
                    safe="", so the mapping is stable and reversible via unquote).
  - predicate IRI: kl:<predicate>  (predicates are already a closed, safe vocabulary --
                    see graph_guard/schema.py PREDICATES).
  - type IRI:      kl:<Type>  from the node's `type` field (e.g. kl:Project).
  - node name:     emitted as `schema:name` (not rdfs:label) -- Task 3's SHACL required-name
                    check is written against schema:name.

Provenance/confidence (D1 -- standard RDF reification, not RDF-star):
  This rdflib build has no ttlstar plugin, and the downstream SHACL/owlrl toolchain is only
  reliable over plain RDF. So each edge produces BOTH:
    1. the asserted triple   <src IRI> <predicate IRI> <dst IRI>   (what SPARQL property
       paths and owlrl reason over), and
    2. a reification block on a deterministically minted statement IRI `kl:stmt/<n>` (n =
       the edge's position in TripleStore.all_edges(), stable because SQLite returns rows in
       insertion/PK order for a given store):
         kl:stmt/<n>  a rdf:Statement ;
                      rdf:subject   <src IRI> ;
                      rdf:predicate <predicate IRI> ;
                      rdf:object    <dst IRI> ;
                      kl:confidence "<confidence>"^^xsd:decimal ;
                      kl:provenance "<note_path>" ;   # omitted if null
                      kl:span       "<span>" .        # omitted if null
  A minted IRI (rather than a random/blank bnode) keeps the export deterministic so tests
  can assert on it directly.
"""
from __future__ import annotations

from urllib.parse import quote

from rdflib import RDF, Graph, Literal, Namespace, URIRef
from rdflib.namespace import XSD

KL = Namespace("https://jott2121.github.io/graph-guard/ns#")
SCHEMA = Namespace("https://schema.org/")
SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")

_SAFE = "-_"  # everything else outside [A-Za-z0-9] gets percent-encoded


def node_iri(node_id: str) -> URIRef:
    """Deterministic node IRI: kl:n/<percent-encoded id>. Same id -> same IRI; any string
    (spaces, slashes, unicode) yields a valid, parseable IRI."""
    return KL[f"n/{quote(str(node_id), safe=_SAFE)}"]


def predicate_iri(predicate: str) -> URIRef:
    return KL[predicate]


def type_iri(type_name: str) -> URIRef:
    return KL[type_name]


def stmt_iri(index: int) -> URIRef:
    return KL[f"stmt/{index}"]


def _bind_namespaces(g: Graph) -> None:
    g.bind("kl", KL)
    g.bind("schema", SCHEMA)
    g.bind("skos", SKOS)


def store_to_graph(store) -> Graph:
    """Build an in-memory rdflib.Graph from a TripleStore. Pure: touches only the store's
    read methods, never writes to disk."""
    g = Graph()
    _bind_namespaces(g)

    for node in store.all_nodes():
        n_iri = node_iri(node["id"])
        g.add((n_iri, RDF.type, type_iri(node["type"])))
        g.add((n_iri, SCHEMA.name, Literal(node["name"])))

    for i, edge in enumerate(store.all_edges()):
        s_iri = node_iri(edge["src"])
        p_iri = predicate_iri(edge["predicate"])
        o_iri = node_iri(edge["dst"])
        g.add((s_iri, p_iri, o_iri))

        stmt = stmt_iri(i)
        g.add((stmt, RDF.type, RDF.Statement))
        g.add((stmt, RDF.subject, s_iri))
        g.add((stmt, RDF.predicate, p_iri))
        g.add((stmt, RDF.object, o_iri))
        g.add((stmt, KL.confidence, Literal(edge["confidence"], datatype=XSD.decimal)))
        if edge.get("note_path"):
            g.add((stmt, KL.provenance, Literal(edge["note_path"])))
        if edge.get("span"):
            g.add((stmt, KL.span, Literal(edge["span"])))

    return g


def export_turtle(store, path=None) -> str:
    """Serialize the store to Turtle. Writes to `path` if given; always returns the string."""
    ttl = store_to_graph(store).serialize(format="turtle")
    if path is not None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(ttl)
    return ttl
