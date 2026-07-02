"""Lean, closed ontology vocabulary for the personal knowledge graph.

Right-sized on purpose: a small CLOSED predicate set gives higher extraction precision and
keeps LLM-generated graph queries reliable (over-formalized OWL hurts LLM querying —
arXiv:2507.09389). Full OWL/SKOS richness lives in the Tier-B RDF export, not here."""
from __future__ import annotations

ENTITY_TYPES = {
    "Note", "Person", "Project", "Reference", "Feedback",
    "Decision", "Claim", "Source", "Tool", "Event", "Concept",
}

# Closed predicate vocabulary (subject -> object relation).
PREDICATES = {
    "mentions", "about", "is_part_of", "authored_by", "created_by",
    "supersedes", "blocks", "depends_on", "decides", "supports", "refutes",
    "derived_from", "broader", "narrower", "related", "has_status",
}

# Single-valued predicates: a conflicting object signals a contradiction (used by guards).
FUNCTIONAL = {"has_status", "supersedes"}

# filename-prefix -> entity type (matches the memory-vault naming convention)
_PREFIX_TYPE = {
    "project_": "Project",
    "reference_": "Reference",
    "feedback_": "Feedback",
    "user_": "Person",
}


def node_type(note_id: str, frontmatter: dict | None = None) -> str:
    """Infer a node's entity type: explicit frontmatter `type:` wins (if a known type),
    else filename prefix, else default 'Note'. Unknown declared types fall back to 'Note'
    (closed vocabulary)."""
    fm = frontmatter or {}
    declared = fm.get("type")
    if isinstance(declared, str):
        t = declared.strip().capitalize()
        if t in ENTITY_TYPES:
            return t
    base = note_id.rsplit("/", 1)[-1].lower()
    for prefix, t in _PREFIX_TYPE.items():
        if base.startswith(prefix):
            return t
    return "Note"


def is_valid_predicate(p: str) -> bool:
    return p in PREDICATES
