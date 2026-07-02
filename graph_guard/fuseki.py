"""SPARQL query layer over the RDF export (Tier B, Task 4).

Two paths, deliberately split (D4/D5 -- see docs/superpowers/specs/
2026-07-01-graph-guard-tierB.md):

  1. `run_sparql` -- the TESTED core. Executes a SELECT against an
     in-memory `rdflib.Graph` built by `rdf_export.store_to_graph`.
     `rdflib.Graph.query()` implements SPARQL 1.1, including property
     paths (`kl:supersedes+`), so every demo query below runs serverless,
     fast, and fully covered by tests/test_fuseki.py. No server required
     for the suite.
  2. `FusekiClient` -- an HTTP client for a real Apache Jena Fuseki
     server, used only when the env var GRAPH_GUARD_FUSEKI_LIVE=1 is set
     (see tests/test_fuseki.py::test_live_fuseki_roundtrip and
     scripts/run-fuseki.sh). Every method that does actual network I/O is
     `# pragma: no cover`, so CI stays green without a running server.
     Uses stdlib `urllib.request` only -- no new dependency.

Demo queries (the Tier B "architect artifact" set):
  - `supersedes_chain` -- multi-hop property path over `kl:supersedes+`.
  - `nodes_of_type`    -- type-filtered retrieval (`?n a kl:<Type>`).
  - `broader_rollup`   -- thematic rollup over `kl:broader+`.
"""
from __future__ import annotations

import json
import urllib.request
from urllib.parse import unquote, urlencode

from rdflib import Graph

from graph_guard.rdf_export import KL, SCHEMA, SKOS, node_iri, type_iri

PREFIXES = f"""\
PREFIX kl: <{KL}>
PREFIX schema: <{SCHEMA}>
PREFIX skos: <{SKOS}>
"""


def run_sparql(query: str, graph: Graph) -> list[dict]:
    """Execute a SPARQL SELECT against an in-memory `rdflib.Graph`.

    Returns rows as `list[dict]`, keyed by SPARQL variable name (no
    leading `?`). Bound values are coerced to plain Python `str` (both
    URIRefs and Literals stringify to their lexical form); an unbound
    optional variable comes back as `None`. This is the pure, fully
    covered core every demo query below -- and the Fuseki client's
    JSON-parsing path -- return their rows in.
    """
    result = graph.query(query)
    rows = []
    for binding in result:
        rows.append(
            {str(var): (str(value) if value is not None else None) for var, value in zip(result.vars, binding)}
        )
    return rows


def _iri_to_id(iri: str) -> str:
    """Inverse of `rdf_export.node_iri`: strip the `kl:n/` prefix and
    percent-decode back to the original node id (node_iri's docstring
    guarantees this round-trips via `unquote`)."""
    prefix = f"{KL}n/"
    if iri.startswith(prefix):
        return unquote(iri[len(prefix):])
    return iri


def _supersedes_chain_query(start_id: str) -> str:
    return PREFIXES + f"""
SELECT ?x WHERE {{
    <{node_iri(start_id)}> kl:supersedes+ ?x .
}}
"""


def supersedes_chain(graph: Graph, start_id: str) -> list[str]:
    """Every node transitively superseded by `start_id`, walking the
    asserted `kl:supersedes` edges via the SPARQL 1.1 property path
    `kl:supersedes+` (one-or-more hops).

    This is the property-path answer to "what did X supersede,
    transitively?" -- a plain `kl:supersedes` (no `+`) query would only
    find the direct, one-hop target. Task 6 contrasts this exact-closure
    answer against PageRank's ranked multi-hop retrieval over the same
    asserted edges.

    Returns bare node ids (not full IRIs), recovered via `_iri_to_id`.
    """
    rows = run_sparql(_supersedes_chain_query(start_id), graph)
    return [_iri_to_id(row["x"]) for row in rows]


def nodes_of_type(graph: Graph, type_name: str) -> list[str]:
    """Type-filtered retrieval: the `schema:name` of every node asserted
    `a kl:<type_name>`.

    The type is injected via rdflib's own N3 term serialization
    (`type_iri(type_name).n3()`), not hand-wrapped as `<{type_iri(type_name)}>`,
    so the query stays well-formed and injection-safe regardless of what
    `type_name` contains. rdflib's `URIRef.n3()` refuses to serialize a term
    containing any of the characters an IRI reference can never legally
    contain (`<`, `>`, `"`, space, `{`, `}`, `|`, `\\`, `^`, backtick) --
    which is exactly the character set needed to close a SPARQL `<...>` IRI
    literal and splice in additional query text -- raising instead of
    emitting anything. That raise is caught below and treated the same as
    "no such type": a hostile `type_name` can therefore never smuggle extra
    query clauses in, and this function never raises or returns spurious
    rows for it -- it simply matches nothing (see
    tests/test_fuseki.py::test_nodes_of_type_is_injection_safe).
    """
    try:
        type_term = type_iri(type_name).n3()
    except Exception:
        return []
    query = PREFIXES + f"""
SELECT ?name WHERE {{
    ?n a {type_term} .
    ?n schema:name ?name .
}}
"""
    return [row["name"] for row in run_sparql(query, graph)]


def broader_rollup(graph: Graph, start_id: str) -> list[str]:
    """Thematic rollup over the concept hierarchy: every concept reachable
    from `start_id` via one-or-more `kl:broader` hops (`kl:broader+`).

    NOTE: the ontology declares `kl:broader rdfs:subPropertyOf
    skos:broader` (ontology/ontology.ttl). That means the SAME rollup is
    also answerable with `skos:broader+` -- but only AFTER an owlrl
    reasoner (Task 5) has materialized the subproperty entailment; the raw
    exported instance data only asserts `kl:broader` directly. This helper
    deliberately queries `kl:broader+`, not `skos:broader+`, so it works
    unmodified on raw exported data without requiring a reasoning pass.

    Returns bare node ids (not full IRIs), recovered via `_iri_to_id`.
    """
    query = PREFIXES + f"""
SELECT ?x WHERE {{
    <{node_iri(start_id)}> kl:broader+ ?x .
}}
"""
    return [_iri_to_id(row["x"]) for row in run_sparql(query, graph)]


def parse_sparql_json(body: str) -> list[dict]:
    """Parse a SPARQL 1.1 JSON Results document (the format Fuseki's
    `/sparql` endpoint returns for `Accept: application/sparql-results+json`)
    into the same `list[dict]` shape `run_sparql` returns.

    Pure and I/O-free, so it's unit-tested directly from a canned JSON
    string (tests/test_fuseki.py::test_fuseki_json_parsing) without a live
    server; `FusekiClient.query` is a thin network wrapper around this.
    """
    doc = json.loads(body)
    variables = doc.get("head", {}).get("vars", [])
    rows = []
    for binding in doc.get("results", {}).get("bindings", []):
        cell = binding
        rows.append({var: (cell[var]["value"] if var in cell else None) for var in variables})
    return rows


class FusekiClient:
    """Thin HTTP client for a live Apache Jena Fuseki server (opt-in, D5).

    Only used when GRAPH_GUARD_FUSEKI_LIVE=1 is set -- see
    tests/test_fuseki.py::test_live_fuseki_roundtrip and
    scripts/run-fuseki.sh, which starts a local Fuseki matching the
    endpoint layout assumed here.

    Expected Fuseki endpoint layout for a dataset (default name `kg`,
    matching scripts/run-fuseki.sh's `--mem /kg`):
      - `endpoint`                 e.g. "http://localhost:3030/kg"
      - `<endpoint>/data?default`  graph store protocol data endpoint --
        POST Turtle here to load it into the dataset's default graph
        (`load_turtle`).
      - `<endpoint>/sparql`        SPARQL query endpoint -- POST a SPARQL
        string here, `Accept: application/sparql-results+json`
        (`query`).

    Every method below performs real network I/O and is excluded from
    coverage (`# pragma: no cover`); the JSON-parsing logic it calls
    (`parse_sparql_json`) is factored out and IS covered.
    """

    def __init__(self, endpoint: str):
        self.endpoint = endpoint.rstrip("/")

    def load_turtle(self, ttl: str) -> None:  # pragma: no cover -- network I/O, opt-in live path only
        req = urllib.request.Request(
            f"{self.endpoint}/data?default",
            data=ttl.encode("utf-8"),
            method="POST",
            headers={"Content-Type": "text/turtle; charset=utf-8"},
        )
        with urllib.request.urlopen(req) as resp:
            resp.read()

    def query(self, sparql: str) -> list[dict]:  # pragma: no cover -- network I/O, opt-in live path only
        data = urlencode({"query": sparql}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.endpoint}/sparql",
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/sparql-results+json",
            },
        )
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
        return parse_sparql_json(body)
