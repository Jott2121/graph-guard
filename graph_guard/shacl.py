"""SHACL validation of exported RDF instance data (Tier B, Task 3).

`graph_guard/ontology_data/shapes.ttl` constrains the INSTANCE graphs produced
by `graph_guard.rdf_export.store_to_graph` (kl: entity type required,
schema:name required, functional predicates single-valued). This module loads
those shapes and runs `pyshacl.validate` over a data graph -- no validation
logic lives here, the shapes file is the source of truth. Loaded via
`importlib.resources` (not a bare filesystem path) so it works both from an
editable checkout and from an installed wheel.
"""
from __future__ import annotations

from importlib import resources

import pyshacl
from rdflib import Graph


def _shapes_path():
    """A `Traversable` pointing at the packaged shapes.ttl."""
    return resources.files("graph_guard").joinpath("ontology_data/shapes.ttl")


def load_shapes() -> Graph:
    """Parse the packaged `ontology_data/shapes.ttl` and return it as an rdflib Graph."""
    g = Graph()
    with resources.as_file(_shapes_path()) as p:
        g.parse(p, format="turtle")
    return g


def validate(data_graph: Graph) -> tuple[bool, Graph, str]:
    """Validate `data_graph` against `graph_guard/ontology_data/shapes.ttl`.

    Thin wrapper over `pyshacl.validate`. Args passed deliberately, and why:
      - shacl_graph=load_shapes()  -- our shapes, not pyshacl's own default.
      - inference='none'           -- no RDFS/OWL materialization before
        validating. The exported instance data already asserts rdf:type and
        schema:name directly (graph_guard/rdf_export.py), so no reasoning is
        needed to see them; skipping it keeps results deterministic and fast
        and avoids owl:Thing/rdfs:Resource inferred triples (Task 5's owlrl
        demo is a separate, explicit reasoning step, not folded into
        validation).
      - advanced=False             -- shapes here are plain SHACL Core
        (sh:targetClass / sh:targetSubjectsOf / sh:property), no SHACL-SPARQL
        extensions, so the advanced feature set isn't needed.

    Returns (conforms, results_graph, results_text) -- pyshacl's own tuple,
    passed through unchanged.
    """
    conforms, results_graph, results_text = pyshacl.validate(
        data_graph,
        shacl_graph=load_shapes(),
        inference="none",
        advanced=False,
    )
    return conforms, results_graph, results_text
