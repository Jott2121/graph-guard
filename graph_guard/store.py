"""SQLite triple store for the personal knowledge graph.

Pragmatic, LPG-flavored triples: edges carry provenance (note_path, span) + confidence,
which pure RDF makes awkward (RDF edges are URI-only). stdlib sqlite3 only. The RDF/OWL
export is Tier B."""
from __future__ import annotations

import json
import sqlite3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    note_path TEXT,
    attrs TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS edges (
    src TEXT NOT NULL,
    predicate TEXT NOT NULL,
    dst TEXT NOT NULL,
    note_path TEXT,
    span TEXT,
    confidence REAL NOT NULL DEFAULT 1.0,
    extractor TEXT NOT NULL DEFAULT 'unknown',
    PRIMARY KEY (src, predicate, dst, note_path)
);
CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src, predicate);
CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst, predicate);
"""


class TripleStore:
    def __init__(self, path=":memory:"):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)

    def upsert_node(self, node):
        self.conn.execute(
            "INSERT OR REPLACE INTO nodes(id,type,name,note_path,attrs) VALUES (?,?,?,?,?)",
            (node["id"], node.get("type", "Note"), node.get("name", node["id"]),
             node.get("note_path"), json.dumps(node.get("attrs", {}))),
        )
        self.conn.commit()

    def upsert_edge(self, edge):
        self.conn.execute(
            "INSERT OR REPLACE INTO edges(src,predicate,dst,note_path,span,confidence,extractor)"
            " VALUES (?,?,?,?,?,?,?)",
            (edge["src"], edge["predicate"], edge["dst"], edge.get("note_path"),
             edge.get("span"), float(edge.get("confidence", 1.0)),
             edge.get("extractor", "unknown")),
        )
        self.conn.commit()

    def node(self, node_id):
        r = self.conn.execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone()
        return self._node_row(r) if r else None

    def all_nodes(self):
        return [self._node_row(r) for r in self.conn.execute("SELECT * FROM nodes")]

    def all_edges(self):
        return [self._edge_row(r) for r in self.conn.execute("SELECT * FROM edges")]

    def neighbors(self, node_id, direction="both"):
        rows = []
        if direction in ("out", "both"):
            rows += self.conn.execute("SELECT * FROM edges WHERE src=?", (node_id,)).fetchall()
        if direction in ("in", "both"):
            rows += self.conn.execute("SELECT * FROM edges WHERE dst=?", (node_id,)).fetchall()
        return [self._edge_row(r) for r in rows]

    def adjacency(self):
        """Symmetric weighted adjacency {node: {neighbor: weight}} for PageRank / multi-hop."""
        adj = {}
        for r in self.conn.execute("SELECT src,dst,confidence FROM edges"):
            w = float(r["confidence"])
            adj.setdefault(r["src"], {})
            adj.setdefault(r["dst"], {})
            adj[r["src"]][r["dst"]] = adj[r["src"]].get(r["dst"], 0.0) + w
            adj[r["dst"]][r["src"]] = adj[r["dst"]].get(r["src"], 0.0) + w
        return adj

    def counts(self):
        n = self.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        e = self.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        return {"nodes": n, "edges": e}

    def close(self):
        self.conn.close()

    @staticmethod
    def _node_row(r):
        return {"id": r["id"], "type": r["type"], "name": r["name"],
                "note_path": r["note_path"], "attrs": json.loads(r["attrs"])}

    @staticmethod
    def _edge_row(r):
        return {"src": r["src"], "predicate": r["predicate"], "dst": r["dst"],
                "note_path": r["note_path"], "span": r["span"],
                "confidence": r["confidence"], "extractor": r["extractor"]}
