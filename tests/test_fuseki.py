import json
import os

import pytest

from graph_guard.fuseki import (
    FusekiClient,
    _iri_to_id,
    _supersedes_chain_query,
    broader_rollup,
    nodes_of_type,
    parse_sparql_json,
    run_sparql,
    supersedes_chain,
)
from graph_guard.rdf_export import export_turtle, store_to_graph
from graph_guard.store import TripleStore


def _chain_store():
    """A -> B -> C -> D via `supersedes`. A 1-hop query only finds B; the
    property-path query (`kl:supersedes+`) must find B, C, and D."""
    s = TripleStore()
    for node_id in ("A", "B", "C", "D"):
        s.upsert_node({"id": node_id, "type": "Project", "name": f"Project {node_id}"})
    s.upsert_edge({"src": "A", "predicate": "supersedes", "dst": "B"})
    s.upsert_edge({"src": "B", "predicate": "supersedes", "dst": "C"})
    s.upsert_edge({"src": "C", "predicate": "supersedes", "dst": "D"})
    return s


def _typed_store():
    s = TripleStore()
    s.upsert_node({"id": "P1", "type": "Project", "name": "Project One"})
    s.upsert_node({"id": "P2", "type": "Project", "name": "Project Two"})
    s.upsert_node({"id": "H1", "type": "Person", "name": "Gina"})
    return s


def _concept_store():
    """X -> Y -> Z via `broader` (X's broader concept is Y, Y's is Z)."""
    s = TripleStore()
    for node_id in ("X", "Y", "Z"):
        s.upsert_node({"id": node_id, "type": "Concept", "name": node_id})
    s.upsert_edge({"src": "X", "predicate": "broader", "dst": "Y"})
    s.upsert_edge({"src": "Y", "predicate": "broader", "dst": "Z"})
    return s


def test_supersedes_chain_multi_hop():
    g = store_to_graph(_chain_store())
    assert set(supersedes_chain(g, "A")) == {"B", "C", "D"}


def test_supersedes_chain_no_results():
    g = store_to_graph(_chain_store())
    assert supersedes_chain(g, "D") == []


def test_nodes_of_type():
    g = store_to_graph(_typed_store())
    result = nodes_of_type(g, "Project")
    assert set(result) == {"Project One", "Project Two"}
    assert "Gina" not in result


def test_nodes_of_type_is_injection_safe():
    """A hostile type_name that tries to break out of the `<...>` IRI
    literal and splice in a UNION clause must not raise and must not
    return spurious rows -- it should simply match nothing, exactly like
    any other type_name with no matching kl: instances."""
    g = store_to_graph(_typed_store())
    hostile = "Project> . } UNION { ?n a <x> . ?n schema:name ?name "
    result = nodes_of_type(g, hostile)
    assert result == []


def test_broader_rollup():
    g = store_to_graph(_concept_store())
    assert set(broader_rollup(g, "X")) == {"Y", "Z"}


def test_run_sparql_returns_dicts():
    g = store_to_graph(_chain_store())
    query = """
    PREFIX kl: <https://jott2121.github.io/graph-guard/ns#>
    SELECT ?s ?o WHERE { ?s kl:supersedes ?o . }
    """
    rows = run_sparql(query, g)
    assert isinstance(rows, list)
    assert len(rows) == 3
    assert all(isinstance(row, dict) for row in rows)
    assert all(set(row.keys()) == {"s", "o"} for row in rows)
    assert all(isinstance(row["s"], str) and isinstance(row["o"], str) for row in rows)


def test_fuseki_json_parsing():
    """Feed a canned SPARQL 1.1 JSON Results string (no server involved) and
    confirm it parses to the same list[dict] shape run_sparql produces."""
    body = json.dumps(
        {
            "head": {"vars": ["x"]},
            "results": {
                "bindings": [
                    {"x": {"type": "uri", "value": "https://example.org/ns#n/B"}},
                    {"x": {"type": "uri", "value": "https://example.org/ns#n/C"}},
                ]
            },
        }
    )
    rows = parse_sparql_json(body)
    assert rows == [
        {"x": "https://example.org/ns#n/B"},
        {"x": "https://example.org/ns#n/C"},
    ]


def test_fuseki_json_parsing_unbound_var_is_none():
    body = json.dumps(
        {
            "head": {"vars": ["x", "y"]},
            "results": {"bindings": [{"x": {"type": "literal", "value": "only-x"}}]},
        }
    )
    rows = parse_sparql_json(body)
    assert rows == [{"x": "only-x", "y": None}]


def test_iri_to_id_passes_through_non_kl_iri():
    """Defensive fallback: an IRI outside the kl:n/ namespace (shouldn't
    happen for well-formed exports, but query results aren't guaranteed to
    stay inside it) is returned unchanged rather than mangled."""
    assert _iri_to_id("https://example.org/other#thing") == "https://example.org/other#thing"


def test_fuseki_client_normalizes_endpoint():
    """Constructing the client and storing the endpoint does no network I/O,
    so it's covered even when the live test below is skipped."""
    client = FusekiClient("http://localhost:3030/kg/")
    assert client.endpoint == "http://localhost:3030/kg"


@pytest.mark.skipif(
    not os.environ.get("GRAPH_GUARD_FUSEKI_LIVE"),
    reason="needs a running Fuseki server; see scripts/run-fuseki.sh. "
    "Set GRAPH_GUARD_FUSEKI_LIVE=1 (and GRAPH_GUARD_FUSEKI_ENDPOINT if not "
    "the default http://localhost:3030/kg) to exercise this test.",
)
def test_live_fuseki_roundtrip():  # pragma: no cover -- exercised only against a real server
    store = _chain_store()
    ttl = export_turtle(store)
    endpoint = os.environ.get("GRAPH_GUARD_FUSEKI_ENDPOINT", "http://localhost:3030/kg")
    client = FusekiClient(endpoint)
    client.load_turtle(ttl)

    # Same query text supersedes_chain() runs in-memory -- proves the live
    # Fuseki path answers identically to rdflib's in-memory engine.
    rows = client.query(_supersedes_chain_query("A"))
    remote = {row["x"] for row in rows}
    in_memory = set(supersedes_chain(store_to_graph(store), "A"))

    # remote rows are full IRIs; in_memory results are bare ids -- recover
    # the bare id via the canonical inverse of node_iri (fuseki.py's own
    # _iri_to_id) rather than re-deriving the id <-> IRI mapping here.
    remote_ids = {_iri_to_id(iri) for iri in remote}
    assert remote_ids == in_memory == {"B", "C", "D"}
