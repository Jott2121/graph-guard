"""Three-tier extraction from markdown notes into typed graph triples.

Tier 1 (frontmatter) + Tier 2 (wikilinks) are deterministic and free — they carry most of
the graph. Tier 3 (an injectable, schema-constrained LLM) fills residual prose and is
optional (default off). Read-only: never writes to the vault."""
from __future__ import annotations

import os
import re

from graph_guard import schema

_FM = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_WIKILINK = re.compile(r"\[\[([^\]|#]+)(?:[#][^\]|]+)?(?:\|[^\]]+)?\]\]")
_HEADING = re.compile(r"^#{1,6}\s+(.*)$")


def parse_frontmatter(text):
    """Minimal YAML-frontmatter parser for common Obsidian patterns (scalars + inline lists).
    Returns (frontmatter_dict, body_without_frontmatter)."""
    m = _FM.match(text)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).splitlines():
        if ":" not in line or line.strip().startswith("#"):
            continue
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip()
        if not key:
            continue
        if val.startswith("[") and val.endswith("]"):
            fm[key] = [v.strip().strip('"\'') for v in val[1:-1].split(",") if v.strip()]
        elif val:
            fm[key] = val.strip('"\'')
        else:
            fm[key] = None
    return fm, text[m.end():]


def _wikilinks(s):
    return [t.strip() for t in _WIKILINK.findall(s) if t.strip()]


def _predicate_for_heading(heading):
    h = (heading or "").lower()
    if "supersede" in h:
        return "supersedes"
    if "decision" in h or "decide" in h:
        return "decides"
    return "mentions"


def extract_note(note_id, text, frontmatter=None):
    """Return (nodes, edges) for one note. frontmatter is parsed from text if not given."""
    parsed_fm, body = parse_frontmatter(text)
    fm = parsed_fm if frontmatter is None else frontmatter
    ntype = schema.node_type(note_id, fm)
    name = os.path.basename(note_id).rsplit(".", 1)[0]
    nodes = {note_id: {"id": note_id, "type": ntype, "name": name,
                       "note_path": note_id, "attrs": {}}}
    edges = []

    def ensure(nid, nt="Note"):
        if nid not in nodes:
            nodes[nid] = {"id": nid, "type": nt, "name": nid, "note_path": None, "attrs": {}}

    # Tier 1 — frontmatter
    for tag in _aslist(fm.get("tags")):
        ensure(tag, "Concept")
        edges.append(_edge(note_id, "about", tag, note_id, "frontmatter"))
    for field, pred in (("project", "is_part_of"), ("people", "mentions"),
                        ("author", "authored_by"), ("authors", "authored_by")):
        for v in _aslist(fm.get(field)):
            tgt = _delink(v)
            ensure(tgt)
            edges.append(_edge(note_id, pred, tgt, note_id, "frontmatter"))
    status = fm.get("status")
    if isinstance(status, str) and status:
        ensure(status, "Concept")
        edges.append(_edge(note_id, "has_status", status, note_id, "frontmatter"))

    # Tier 2 — body wikilinks, typed by the current heading
    heading = None
    for line in body.splitlines():
        hm = _HEADING.match(line)
        if hm:
            heading = hm.group(1)
            continue
        for tgt in _wikilinks(line):
            ensure(tgt)
            edges.append(_edge(note_id, _predicate_for_heading(heading), tgt, note_id, "wikilink"))

    return list(nodes.values()), edges


def build_graph(roots, store, *, llm_fn=None):
    """Walk markdown under roots, extract, upsert into the store. llm_fn(note_id, text)
    -> [(s,p,o)] is optional (Tier 3); triples with invalid predicates are dropped."""
    counts = {"notes": 0, "nodes": 0, "edges": 0}
    for path in _walk_md(roots):
        try:
            text = open(path, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        counts["notes"] += 1
        nodes, edges = extract_note(path, text)
        if llm_fn is not None:
            for triple in (llm_fn(path, text) or []):
                s, p, o = triple
                if schema.is_valid_predicate(p):
                    edges.append(_edge(s, p, o, path, "llm"))
        for n in nodes:
            store.upsert_node(n); counts["nodes"] += 1
        for e in edges:
            store.upsert_edge(e); counts["edges"] += 1
    return counts


def _aslist(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _delink(v):
    if not isinstance(v, str):
        return v
    m = _WIKILINK.search(v)
    return m.group(1).strip() if m else v.strip()


def _edge(src, predicate, dst, note_path, extractor, confidence=1.0):
    return {"src": src, "predicate": predicate, "dst": dst, "note_path": note_path,
            "span": None, "confidence": confidence, "extractor": extractor}


def _walk_md(roots):
    skip = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache"}
    for root in roots:
        if os.path.isfile(root):
            if root.endswith(".md"):
                yield root
            continue
        for dp, dn, fn in os.walk(root):
            dn[:] = [d for d in dn if d not in skip]
            for name in sorted(fn):
                if name.endswith(".md"):
                    yield os.path.join(dp, name)
