# examples

A tiny, self-contained demo of the one thing graph-guard is for: answering a **multi-hop**
question that plain lexical RAG cannot. No API key, no model, no vault of your own — just 7
markdown notes and deterministic extraction.

```bash
pip install -e .          # from the repo root
python examples/run_sample.py
```

## What it shows

`sample_vault/` is 7 notes. Three of them form a relationship chain:

```
cache-eviction.md  --is_part_of-->  search-revamp.md  --owned/authored_by-->  maya-chen.md
```

The question is **"p99 cache eviction latency owner"** — i.e. *who owns this bug?* The owner,
Maya, is never written next to the bug. Her note does not contain the words "cache", "eviction",
"p99", or "latency". So:

- **Lexical (plain TF-IDF)** scores `maya-chen.md` at **0.00**. It can only match text that
  looks like the query, and hers doesn't. It cannot find the owner.
- **The graph** anchors the query to `cache-eviction.md`, runs Personalized PageRank across the
  typed edges, and gives `maya-chen.md` **real relevance (~0.05)** — ~3,000x the unrelated
  notes — by walking two hops to the person who owns the project the bug belongs to.

That gap is the multi-hop lift the repo measures at scale (+14% hit@10, +26% MRR on a real
517-note vault). The example also runs a **simple lookup** to show the graph falls back to
lexical and does not hurt the easy case.

## Expected output

```
built graph over 7 notes: {'nodes': 11, 'edges': 12}

QUERY (multi-hop): "p99 cache eviction latency owner"

the query anchors to graph node: ['cache-eviction.md']

GRAPH relevance (PPR from the anchor x specificity):
  cache-eviction.md      0.120435   <- the anchor (the symptom)
  search-revamp.md       0.107982   <- 1 hop: the project the bug is part of
  vector-index.md        0.067981   <- also part of that project
  maya-chen.md           0.050109   <- 2 hops: she OWNS the project   *** the answer ***
  travel-policy.md       0.000016
  onboarding.md          0.000016
  incident-runbook.md    0.000016

LEXICAL relevance (plain TF-IDF, what vanilla RAG sees):
  cache-eviction.md      0.626911
  incident-runbook.md    0.000000
  maya-chen.md           0.000000
  onboarding.md          0.000000
  search-revamp.md       0.000000
  travel-policy.md       0.000000
  vector-index.md        0.000000

...
QUERY (simple lookup): "travel reimbursement per diem"
  graph-aware top hit : travel-policy.md
  lexical top hit     : travel-policy.md
  -> they agree.
```

Open `run_sample.py` — it uses the same public pieces the shipped retriever does
(`link_entities`, `personalized_pagerank`, `node_specificity`), so what you see here is the
graph leg of `GraphRetriever.retrieve()`, not a mock.
