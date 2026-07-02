#!/usr/bin/env bash
# scripts/run-fuseki.sh -- stand up a local Apache Jena Fuseki server for the
# LIVE half of Tier B's SPARQL layer (graph_guard/fuseki.py::FusekiClient).
#
# NOT part of the automated test suite. tests/test_fuseki.py's
# test_live_fuseki_roundtrip is `pytest.mark.skipif`-skipped unless you set
# GRAPH_GUARD_FUSEKI_LIVE=1 *and* actually have a server running (started by
# this script). CI never runs this; graph_guard/fuseki.py's `run_sparql`
# path (rdflib's in-memory SPARQL engine) is the tested query engine for the
# whole suite (D4/D5 in docs/superpowers/specs/2026-07-01-graph-guard-tierB.md)
# -- this script is a dev/demo convenience, nothing more.
#
# Requirement: a JRE. Fuseki is a JVM app -- `java -version` must work.
#
# What this does:
#   1. Downloads Apache Jena Fuseki (the standalone server distribution)
#      into ./.fuseki/ if not already present, or reuses an existing local
#      install pointed to by $FUSEKI_HOME (skip the download entirely).
#   2. Starts it with an IN-MEMORY dataset named `kg` on port 3030:
#        ./fuseki-server --mem /kg
#      In-memory means nothing persists across restarts -- that's
#      intentional for a local demo/dev loop; re-run this script (which
#      reloads kg.ttl) whenever you restart the server.
#   3. Waits for the server to come up, then loads an exported kg.ttl
#      (default ./kg.ttl, override with $KG_TTL) into the dataset's data
#      endpoint via curl (POST, Content-Type: text/turtle) -- the same
#      graph-store-protocol endpoint FusekiClient.load_turtle() uses.
#   4. Runs Fuseki in the foreground (Ctrl-C to stop). Use another shell for
#      the client/test commands below.
#
# Usage:
#   # 1. produce an export (from a Python shell / your own script):
#   #      from graph_guard.rdf_export import export_turtle
#   #      from graph_guard.store import TripleStore
#   #      export_turtle(TripleStore("path/to/kg.sqlite"), path="kg.ttl")
#   # 2. start Fuseki + auto-load kg.ttl:
#   ./scripts/run-fuseki.sh
#   # (or point at a different export)
#   KG_TTL=/path/to/other.ttl ./scripts/run-fuseki.sh
#
#   # 3. in another shell, exercise the live path:
#   GRAPH_GUARD_FUSEKI_LIVE=1 pytest tests/test_fuseki.py -k live -q
#
# Default endpoint (matches graph_guard.fuseki.FusekiClient's expected
# layout -- see that module's docstring):
#   http://localhost:3030/kg
#     query:  http://localhost:3030/kg/sparql   (SPARQL SELECT, JSON results)
#     data:   http://localhost:3030/kg/data     (graph store protocol, Turtle upload)
#
# Mirror-to-Neptune story: kg.ttl is plain, standards-compliant RDF/Turtle --
# it is exactly what you would bulk-load into Amazon Neptune (or any other
# SPARQL 1.1 triple store) for a production deployment. Fuseki here is a
# free, zero-config, local stand-in for that same SPARQL-over-HTTP
# interface, not a throwaway/incompatible toy format.

set -euo pipefail

FUSEKI_VERSION="${FUSEKI_VERSION:-4.10.0}"
FUSEKI_DIR="${FUSEKI_HOME:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/.fuseki/apache-jena-fuseki-${FUSEKI_VERSION}}"
FUSEKI_TARBALL="apache-jena-fuseki-${FUSEKI_VERSION}.tar.gz"
FUSEKI_URL="https://archive.apache.org/dist/jena/binaries/${FUSEKI_TARBALL}"
DATASET="${FUSEKI_DATASET:-kg}"
PORT="${FUSEKI_PORT:-3030}"
KG_TTL="${KG_TTL:-$(pwd)/kg.ttl}"
ENDPOINT="http://localhost:${PORT}/${DATASET}"

if ! command -v java >/dev/null 2>&1; then
    echo "error: java (a JRE) is required to run Apache Jena Fuseki." >&2
    exit 1
fi

if [ ! -x "${FUSEKI_DIR}/fuseki-server" ]; then
    echo "Fuseki not found at ${FUSEKI_DIR} -- downloading ${FUSEKI_URL} ..."
    mkdir -p "$(dirname "${FUSEKI_DIR}")"
    curl -fL -o "/tmp/${FUSEKI_TARBALL}" "${FUSEKI_URL}"
    tar -xzf "/tmp/${FUSEKI_TARBALL}" -C "$(dirname "${FUSEKI_DIR}")"
    chmod +x "${FUSEKI_DIR}/fuseki-server"
fi

echo "Starting Fuseki: dataset=/${DATASET} port=${PORT} (in-memory, foreground) ..."
(
    cd "${FUSEKI_DIR}"
    ./fuseki-server --mem "/${DATASET}" --port "${PORT}" &
    FUSEKI_PID=$!
    trap 'kill "${FUSEKI_PID}" 2>/dev/null || true' EXIT

    echo -n "Waiting for ${ENDPOINT} to come up"
    for _ in $(seq 1 30); do
        if curl -fs "http://localhost:${PORT}/\$/ping" >/dev/null 2>&1; then
            echo " ready."
            break
        fi
        echo -n "."
        sleep 1
    done

    if [ -f "${KG_TTL}" ]; then
        echo "Loading ${KG_TTL} into ${ENDPOINT}/data ..."
        curl -fs -X POST -H "Content-Type: text/turtle; charset=utf-8" \
            --data-binary "@${KG_TTL}" \
            "${ENDPOINT}/data?default" >/dev/null
        echo "Loaded. Query endpoint: ${ENDPOINT}/sparql"
    else
        echo "No kg.ttl found at ${KG_TTL} -- skipping load. Set KG_TTL=/path/to/export.ttl" >&2
        echo "or POST it yourself: curl -X POST -H 'Content-Type: text/turtle' --data-binary @kg.ttl '${ENDPOINT}/data?default'" >&2
    fi

    wait "${FUSEKI_PID}"
)
