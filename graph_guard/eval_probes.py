"""Deterministic structure-derived probe generator for the Gate D retrieval-lift eval.

The eval has NO relevance labels (personal vault) -- so probes are derived from the KG's own
structure, giving every probe a KNOWN correct answer with no hand-labeling and no RNG:
- multi-hop: query names a note, gold is a note it links to that shares few/no words with
  it -- flat lexical retrieval can't find gold by word overlap, only the graph edge reaches
  it. This is the case the graph SHOULD win.
- simple-lookup: query = a note's own label, gold = that note -- the easy control the graph
  must NOT regress on.
"""
from __future__ import annotations

from dataclasses import dataclass

from rag_guard.retriever import _toks

from graph_guard.graph_retriever import _clean_label
from graph_guard.schema import PREDICATES

# `mentions` is excluded: it's the most generic, near-ubiquitous predicate (almost any note
# can "mention" almost any other), so it wouldn't test genuine multi-hop graph traversal --
# it would just add lexical-coincidence noise to the probe set.
RELATIONAL = frozenset(PREDICATES) - {"mentions"}


@dataclass(frozen=True)
class Probe:
    family: str
    query: str
    gold_id: str


def multi_hop_probes(store, *, max_overlap: int = 1) -> tuple[list[Probe], int]:
    """Build multi-hop probes from RELATIONAL edges between two real notes (have note_path).
    query = clean label of the src note; gold_id = the dst note's id. KEEP the probe only if
    the query and gold clean-label token sets overlap by <= max_overlap (the low-overlap
    filter -- this is what makes it a genuine multi-hop test flat lexical can't win by
    accident); otherwise discard it. Deterministic: edges are visited in `all_edges()` order,
    no randomness. Returns (kept_probes, discarded_count)."""
    nodes = {node["id"]: node for node in store.all_nodes()}
    kept: list[Probe] = []
    discarded = 0
    for edge in store.all_edges():
        if edge["predicate"] not in RELATIONAL:
            continue
        src_node = nodes.get(edge["src"])
        dst_node = nodes.get(edge["dst"])
        if not src_node or not src_node.get("note_path"):
            continue
        if not dst_node or not dst_node.get("note_path"):
            continue
        query = _clean_label(src_node)
        overlap = len(set(_toks(query)) & set(_toks(_clean_label(dst_node))))
        if overlap <= max_overlap:
            kept.append(Probe(family="multi_hop", query=query, gold_id=edge["dst"]))
        else:
            discarded += 1
    return kept, discarded


def simple_lookup_probes(store, *, n: int | None = None) -> list[Probe]:
    """One probe per real note (has note_path): query = its own clean label, gold_id = its own
    id -- high query/gold overlap by construction, the easy-lookup control. Deterministic
    sample: real notes sorted by id, first `n` (or all when n is None); no randomness."""
    notes = sorted(
        (node for node in store.all_nodes() if node.get("note_path")),
        key=lambda node: node["id"],
    )
    if n is not None:
        notes = notes[:n]
    return [
        Probe(family="simple_lookup", query=_clean_label(node), gold_id=node["id"])
        for node in notes
    ]
