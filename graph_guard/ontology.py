"""Loader for the hand-authored OWL T-Box (Tier B).

`graph_guard/ontology_data/ontology.ttl` is the class/property schema that Tier
B's RDF instance data (`graph_guard.rdf_export`) conforms to. This module just
parses it into an `rdflib.Graph` -- no logic lives here, the ontology file is
the source of truth. Loaded via `importlib.resources` (not a bare filesystem
path) so it works both from an editable checkout and from an installed wheel,
where the package may live inside a zip or site-packages tree.
"""
from __future__ import annotations

from importlib import resources

from rdflib import Graph


def _ontology_path():
    """A `Traversable` pointing at the packaged ontology.ttl."""
    return resources.files("graph_guard").joinpath("ontology_data/ontology.ttl")


def load_ontology() -> Graph:
    """Parse the packaged `ontology_data/ontology.ttl` and return it as an rdflib Graph."""
    g = Graph()
    with resources.as_file(_ontology_path()) as p:
        g.parse(p, format="turtle")
    return g
