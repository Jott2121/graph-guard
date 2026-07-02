"""Loader for the hand-authored OWL T-Box (Tier B).

`ontology/ontology.ttl` is the class/property schema that Tier B's RDF instance
data (`graph_guard.rdf_export`) conforms to. This module just parses it into an
`rdflib.Graph` -- no logic lives here, the ontology file is the source of truth.
"""
from __future__ import annotations

from pathlib import Path

from rdflib import Graph

ONTOLOGY_PATH = Path(__file__).resolve().parent.parent / "ontology" / "ontology.ttl"


def load_ontology() -> Graph:
    """Parse `ontology/ontology.ttl` and return it as an rdflib Graph."""
    g = Graph()
    g.parse(ONTOLOGY_PATH, format="turtle")
    return g
