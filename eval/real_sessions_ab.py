"""A/B the graph against lexical baselines using REAL sessions as the label source.

WHY THIS EXISTS. The eval this repo shipped with (`eval/real_vault_lift.py`) derives its
probes from the graph's own structure: a multi-hop query is built from a source note's
label and the gold answer is a note linked to it. That measures whether PageRank can walk
edges the probe generator just handed it. A graph will always win that. It is circular,
and it is not evidence about the questions a human actually asks.

This harness takes its labels from outside the system under test. For each Claude Code
session it uses the first substantive user prompt as the query, and the markdown files that
session went on to OPEN as the gold set. Weak, but independent -- and biased *toward*
breadth-seeking methods, since the gold set spans everything the session needed while the
query is only its opening prompt. A method that surfaces the rest of a spread-out answer
should win under this label. That makes a loss here meaningful.

Arms, each differing from the previous by exactly one thing:
  flat          chunk-level TF-IDF (rag-guard's retriever)
  note          note-level TF-IDF (graph-guard's own lexical leg)
  ensemble      note + chunk merged, NO graph
  ensemble+ppr  the same, with Personalized PageRank fused in

Run:
  python eval/real_sessions_ab.py --roots ~/notes --transcripts ~/.claude/projects/<proj>

Output is aggregate-only: no prompts, no file names, no session ids.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import random
import sys
from math import comb

from rag_guard.corpus import build_corpus
from rag_guard.retriever import Retriever

from graph_guard import service
from graph_guard.graph_retriever import link_entities
from graph_guard.ppr import node_specificity, personalized_pagerank

RRF_K = 60
MIN_PROMPT_CHARS = 25


def _epoch(value):
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return None


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def load_sessions(transcripts_dir, corpus_paths, max_sessions=None):
    """[(query, gold_paths)] -- gold = corpus files the session opened after its first prompt."""
    sessions = []
    for path in sorted(glob.glob(os.path.join(transcripts_dir, "*.jsonl"))):
        query, query_at, touched = None, None, []
        try:
            with open(path, encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    try:
                        entry = json.loads(line)
                    except ValueError:
                        continue
                    when = _epoch(entry.get("timestamp"))
                    message = entry.get("message") or {}
                    content = message.get("content")
                    if entry.get("type") == "user" and query is None:
                        text = content if isinstance(content, str) else " ".join(
                            p.get("text", "") for p in content
                            if isinstance(p, dict) and p.get("type") == "text"
                        ) if isinstance(content, list) else ""
                        text = (text or "").strip()
                        if (text and not text.startswith("<") and "tool_result" not in text
                                and len(text) >= MIN_PROMPT_CHARS):
                            query, query_at = text[:600], when
                    elif isinstance(content, list) and when is not None:
                        for part in content:
                            if isinstance(part, dict) and part.get("type") == "tool_use":
                                touched.append((when, " ".join(_strings(part.get("input") or {}))))
        except OSError:
            continue
        if not query or query_at is None:
            continue
        gold = {p for p in corpus_paths
                for when, blob in touched if when >= query_at and p in blob}
        if gold:
            sessions.append((query, gold))
        if max_sessions and len(sessions) >= max_sessions:
            break
    return sessions


def _rrf(*ranklists):
    scores = {}
    for ranklist in ranklists:
        for i, item in enumerate(ranklist):
            scores[item] = scores.get(item, 0.0) + 1.0 / (RRF_K + i)
    return sorted(scores, key=scores.get, reverse=True)


def _dedup(seq, k):
    out = []
    for item in seq:
        if item not in out:
            out.append(item)
        if len(out) == k:
            break
    return out


def sign_test(baseline, arm):
    wins = sum(1 for a, b in zip(baseline, arm) if b > a)
    losses = sum(1 for a, b in zip(baseline, arm) if b < a)
    n = wins + losses
    if not n:
        return wins, losses, 1.0
    p = sum(comb(n, x) for x in range(0, min(wins, losses) + 1)) / 2 ** n * 2
    return wins, losses, min(p, 1.0)


def run_controls(retrieve_fn, sessions, depth, *, seed=0):
    """Two pre-registered controls. Every methodology error in this repo's history was a
    HARNESS bug, not an analysis bug, so a number is not reportable until the harness has
    demonstrated it can detect a signal and can lose one.

    POSITIVE: query a note with its own verbatim text. If the harness cannot recover the
    note it just quoted, retrieval or the id->path mapping is broken.
    NEGATIVE: shuffle the gold sets across sessions. Recall must collapse. If a shuffled
    label scores near the real one, the metric is measuring note popularity or a path-
    matching artifact rather than query relevance -- which is exactly how a plausible
    number survives a broken harness.
    """
    real = [len(set(retrieve_fn(q)) & gold) / len(gold) for q, gold in sessions]
    real_mean = sum(real) / len(real)

    rng = random.Random(seed)
    golds = [gold for _, gold in sessions]
    shuffled = golds[:]
    rng.shuffle(shuffled)
    # A permutation can map a session onto its own gold; that is fine and left alone,
    # since forcing a derangement would bias the control away from chance.
    control = [len(set(retrieve_fn(q)) & gold) / len(gold)
               for (q, _), gold in zip(sessions, shuffled)]
    control_mean = sum(control) / len(control)

    hits = 0
    probes = 0
    for _, gold in sessions[:25]:
        for path in sorted(gold)[:1]:
            try:
                text = open(path, encoding="utf-8", errors="ignore").read()[:400]
            except OSError:
                continue
            if len(text.split()) < 8:
                continue
            probes += 1
            hits += 1 if path in set(retrieve_fn(text)) else 0

    print("CONTROLS (flat arm)")
    print(f"  positive  verbatim-text queries recovering their own note : "
          f"{hits}/{probes}" + (f" ({hits/probes:.0%})" if probes else ""))
    print(f"  negative  real gold      recall@{depth} : {real_mean:.4f}")
    print(f"            shuffled gold  recall@{depth} : {control_mean:.4f}"
          f"   (ratio {control_mean/real_mean:.2f})" if real_mean else "")
    ok = True
    if probes and hits / probes < 0.8:
        print("  FAIL: harness cannot recover notes it quoted verbatim.", file=sys.stderr)
        ok = False
    if real_mean and control_mean / real_mean > 0.5:
        print("  FAIL: shuffled gold scores too close to real gold; the metric is not "
              "measuring query relevance.", file=sys.stderr)
        ok = False
    return ok


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--roots", required=True, help="colon-separated corpus roots")
    ap.add_argument("--transcripts", required=True, help="dir of Claude Code *.jsonl sessions")
    ap.add_argument("--depth", type=int, default=20)
    ap.add_argument("--max-sessions", type=int, default=None)
    ap.add_argument("--seed", type=int, default=0, help="seed for the shuffled-gold control")
    ap.add_argument("--skip-controls", action="store_true",
                    help="not recommended: the controls are what make the numbers meaningful")
    args = ap.parse_args(argv)

    roots = [os.path.expanduser(r) for r in args.roots.split(":")]
    depth = args.depth

    retriever = service.build_retriever(roots)
    health = service.graph_health(retriever)
    print(f"graph: {health['nodes']} nodes, {health['edges']} edges")
    if health["empty"]:
        # The failure that motivated this harness: an empty KG makes GraphRetriever fall
        # back to lexical, so the "graph" arm silently measures the baseline.
        print("ABORT: the graph is empty; every graph arm would be lexical fallback.",
              file=sys.stderr)
        return 2

    note_tfidf = retriever._tfidf
    chunks = Retriever(build_corpus(roots))
    corpus_paths = sorted({d["id"] for d in retriever._store.all_nodes() if d.get("note_path")}
                          or {n["note_path"] for n in retriever._store.all_nodes()
                              if n.get("note_path")})

    def chunk_notes(query, k):
        seen = []
        for hit in chunks.retrieve(query, k * 4):
            note = hit["id"].split("#")[0]
            for root in roots:
                base = os.path.dirname(root if os.path.isdir(root) else os.path.dirname(root))
                candidate = os.path.join(base, note)
                if os.path.exists(candidate):
                    seen.append(candidate)
                    break
        return seen

    adjacency = retriever._store.adjacency()
    specificity = node_specificity(adjacency)

    def ppr_notes(query):
        seeds = link_entities(query, retriever._store)
        if not seeds:
            return []
        ranks = personalized_pagerank(adjacency, seeds)
        scored = {}
        for node in retriever._store.all_nodes():
            if node.get("note_path"):
                value = ranks.get(node["id"], 0.0) * specificity.get(node["id"], 1.0)
                if value > 0:
                    scored[node["id"]] = value
        return sorted(scored, key=scored.get, reverse=True)

    # Arms are fused with reciprocal rank fusion, NOT concatenated. Concatenation is
    # order-dependent: the first list fills every slot and the second never contributes,
    # which silently turns "note + chunk" into "note".
    arms = {
        "flat": lambda q: _dedup(chunk_notes(q, depth), depth),
        "note": lambda q: _dedup([h["id"] for h in note_tfidf(q, depth)], depth),
        "ensemble": lambda q: _dedup(
            _rrf([h["id"] for h in note_tfidf(q, depth)], chunk_notes(q, depth)), depth),
        "ensemble+ppr": lambda q: _dedup(
            _rrf([h["id"] for h in note_tfidf(q, depth)], chunk_notes(q, depth), ppr_notes(q)),
            depth),
    }

    sessions = load_sessions(args.transcripts, corpus_paths, args.max_sessions)
    if not sessions:
        print("No labelled sessions found.", file=sys.stderr)
        return 1
    print(f"sessions: {len(sessions)}   depth: {depth}\n")

    results = {name: [] for name in arms}
    anchored = 0
    for query, gold in sessions:
        anchored += 1 if link_entities(query, retriever._store) else 0
        for name, fn in arms.items():
            got = set(fn(query))
            results[name].append(len(got & gold) / len(gold))

    print(f"queries linking to >=1 graph anchor: {anchored}/{len(sessions)}\n")

    if not args.skip_controls:
        ok = run_controls(arms["flat"], sessions, depth, seed=args.seed)
        if not ok:
            print("\nABORT: controls failed. The arm numbers below would be meaningless.",
                  file=sys.stderr)
            return 3
        print()
    print(f"{'arm':<16}{'recall@%d' % depth:>12}{'vs ensemble':>28}")
    for name in arms:
        mean = sum(results[name]) / len(results[name])
        if name == "ensemble":
            print(f"{name:<16}{mean:>12.4f}{'(baseline)':>28}")
        else:
            w, l, p = sign_test(results["ensemble"], results[name])
            print(f"{name:<16}{mean:>12.4f}{f'better {w}, worse {l}, p={p:.4f}':>28}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
