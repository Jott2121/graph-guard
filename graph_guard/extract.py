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


# inline relation cue substrings (checked before heading context)
_INLINE_CUES = [("supersed", "supersedes"), ("block", "blocks"),
                ("depend", "depends_on"), ("part of", "is_part_of"),
                ("decid", "decides")]


def _predicate_for_line(line, heading):
    """Type an edge by an inline relation cue in the line, else by heading, else 'mentions'.
    NOTE (Tier A honesty): this is direction-agnostic — 'X superseded by [[Y]]' emits
    (note, supersedes, Y) regardless of who supersedes whom. Symmetric PPR is unaffected;
    precise relation DIRECTION is a Tier-3 (LLM extraction) refinement."""
    low = line.lower()
    for cue, pred in _INLINE_CUES:
        if cue in low:
            return pred
    return _predicate_for_heading(heading)


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

    # Tier 2 — body wikilinks, typed by inline relation cue then heading, else mentions
    heading = None
    for line in body.splitlines():
        hm = _HEADING.match(line)
        if hm:
            heading = hm.group(1)
            continue
        links = _wikilinks(line)
        if not links:
            continue
        pred = _predicate_for_line(line, heading)
        for tgt in links:
            ensure(tgt)
            edges.append(_edge(note_id, pred, tgt, note_id, "wikilink"))

    return list(nodes.values()), edges


def build_graph(roots, store, *, llm_fn=None, resolve_links=True):
    """Walk markdown under roots, extract, resolve wikilinks to real notes, upsert into the
    store. Two passes: (1) collect note basenames; (2) extract + resolve edge/node targets by
    basename so [[leo]] connects to leo.md (real multi-hop). llm_fn(note_id, text)->[(s,p,o)]
    is optional (Tier 3); invalid predicates are dropped."""
    paths = list(_walk_md(roots))
    note_paths = set(paths)
    basename_map = {}
    for p in paths:
        basename_map.setdefault(_basename_key(p), p)
    counts = {"notes": 0, "nodes": 0, "edges": 0}
    for path in paths:
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
        if resolve_links:
            nodes, edges = _resolve(nodes, edges, basename_map, note_paths)
        for n in nodes:
            store.upsert_node(n); counts["nodes"] += 1
        for e in edges:
            store.upsert_edge(e); counts["edges"] += 1
    return counts


def _basename_key(node_id):
    return os.path.basename(node_id).rsplit(".", 1)[0].lower()


def _resolve(nodes, edges, basename_map, note_paths):
    """Rewrite bare wikilink targets to real note ids by basename; a node that IS a real
    note keeps its own id (never dropped on a cross-vault basename collision)."""
    def res(nid):
        if nid in note_paths:
            return nid
        return basename_map.get(_basename_key(nid), nid)
    new_edges = [{**e, "src": res(e["src"]), "dst": res(e["dst"])} for e in edges]
    keep = {}
    for n in nodes:
        rid = res(n["id"])
        if rid != n["id"]:
            continue  # a bare target that resolved to a real note -> drop the duplicate
        keep[n["id"]] = n
    return list(keep.values()), new_edges


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
