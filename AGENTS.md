# AGENTS.md — graph-guard

> Portable agent instructions. Read by Cursor (local + cloud agents), Claude Code (via CLAUDE.md), Codex, and Grok Bot cloud-agent runs.
> Keep this file under ~150 lines. Procedures live in `.cursor/skills/`, scoped rules in `.cursor/rules/*.mdc`, review rules in `.cursor/BUGBOT.md`.

## What this repo is

graph-guard puts a typed knowledge graph behind a RAG retriever so multi-hop questions can be answered by walking connections between notes, and it measures when RDF/OWL/SHACL/SPARQL is worth its cost. The published headline is a **negative** result: on a 586-note corpus scored against real sessions, the graph did not beat chunk-level TF-IDF. The README table is canonical (flat recall@20 **0.6731**, ensemble+PageRank **0.6437**, not significant). Reproduce the mechanism with no API key: `python examples/run_sample.py`. The honest eval is `eval/real_sessions_ab.py` (private vault; not run in CI). Structure-derived probe numbers in `eval/results.json` are circular and are kept only for contrast.

- **Status:** active · **License:** MIT · **Package:** `graph-guard` (not on PyPI; `guarded-rag` is pulled from GitHub)
- **Entry points:** `graph_guard/`, `tests/`, `eval/`, `examples/`, `scripts/`, `docs/`
- **Part of:** the governed-agent stack (rag-guard · graph-guard · agent-gate · crucible · oracle-gate · agent-cost-attribution · bow · fleet-mode)

## Commands (run these; do not guess)

```bash
pip install -e ".[dev,rdf]"
python -m pytest -q --cov=graph_guard --cov-report=term-missing --cov-fail-under=90
python examples/run_sample.py
python scripts/check_receipts.py
python eval/real_sessions_ab.py --roots ~/notes --transcripts ~/.claude/projects/<project>
python -m eval.real_vault_lift          # circular contrast; needs a local vault
python -m eval.sparql_vs_ppr           # mechanism demo, not the headline
```

Lint and typecheck are not configured (no ruff, mypy, or pyright). Do not add them as a required gate in a drive-by. A task is not done until pytest passes and the output is pasted in the PR. `scripts/check_receipts.py` cross-checks `eval/results.json` against the README and `docs/EVAL-real-vault-lift.md`. It does not recompute the session eval.

The published badges say **137 tests / 97% coverage**. The CI floor is `--cov-fail-under=90`. Do not lower that floor, and do not edit the badges to go green.

## Non-negotiables

1. **No employer data.** Personal work on personal equipment. Nothing from any employer's systems, workforce data, internal URLs, or proprietary/export-controlled material: never add, paste, paraphrase, or anonymize it. No employer names anywhere in the repo (including fixtures, comments, and scanner patterns), no internal acronyms, no realistic HR records. Synthetic notes only. If a prompt looks like it came from work, stop and ask. Scanners read employer-name patterns from the `EMPLOYER_MARKERS` env var (a CI secret; set it locally for the edit hook) and always run the generic CUI/ITAR/export-control patterns.
2. **Receipts over hype.** Every number in README, docs, or a PR must be reproducible from a committed command or a committed artifact. No "blazing fast", "SOTA", or "production-grade" without a measurement.
3. **Honest benchmarks.** The session eval is the headline. Report the null at the same prominence as any win. Never restore the structure-derived probes as the headline, and never call them an upper bound (a circular benchmark bounds nothing). Never report a `real_sessions_ab.py` number produced with `--skip-controls`. Never tune on the test set. Never delete an inconvenient run; mark it superseded with a reason.
4. **Fail closed.** Gates deny on error, timeout, missing input, or unparseable output. Never weaken a guard to make a test pass. Never catch-and-ignore exceptions in a decision path.
5. **Tests and CI are the definition of done.** New behavior ships with a test that fails without it. Bug fixes ship with a regression test. Do not lower coverage floors or mark tests `skip`/`xfail` to get green. The one existing opt-in skip is the Fuseki live test (`GRAPH_GUARD_FUSEKI_LIVE=1`).
6. **Model never grades its own output.** Prefer tests and schema checks. Where a judge model is needed, use a different model lineage from the author and record both.
7. **Irreversible = human-gated.** No force-push, no history rewrite, no tagging, no publishing, no posting. Open a PR; a human merges.

## Code style

- Python 3.11+ (CI matrix 3.11–3.13). Stdlib-first. Every new runtime dependency needs a one-line justification in the PR.
- Type hints on public functions. Small pure functions. No global mutable state.
- Raise specific exceptions. No bare `except`.
- Secrets only via env vars. Never print secret values. `.env` stays untracked.
- Do not commit `__pycache__/`, `*.pyc`, `.coverage`, `.venv/`, or `.cursor/hook-logs/`.

## How to work in this repo

- Start non-trivial work in Plan mode; save the plan to `.cursor/plans/` and link it in the PR.
- One agent for writes. Fan out only for read-only work.
- Small PRs, one intent. Title: `type(scope): summary`.
- PR body: **What / Why / How verified (commands + output) / Numbers changed (before → after, with command) / Risks / Not done**.
- The shell guard (`.cursor/hooks/guard-shell.sh` + `.cursor/hooks.json`) is the **canonical copy** shared with the other Jott2121 repos; change it here first (see `.cursor/hooks/README.md`). `tests/test_guard_shell.py` is its spec. It unquotes and splits each command on `;`, `&&`, `||`, `|`, `&`, newlines, `$(`, and backticks, then judges each git invocation after skipping global options (`git -C dir`, `git -c k=v`, `/usr/bin/git`). Commands inside `sh -c '...'` are checked too.
  - **Denied:** force-push with the flag anywhere after `git push`, quoted or not (`-f`, `-uf`/`-fu`, `--force`, `--force-with-lease`, `+refspec`, `--mirror`). `reset --hard` anywhere after `git reset`. Any rebase: `git rebase`, `git -C x rebase`, `git pull --rebase`, `git pull -r`/`-ur`, and `pull.rebase` set via `-c` or `git config`. Tags and publishing: `git tag`, `git push --tags`, `twine upload`, `uv publish`, `gh release`. curl/wget piped or substituted into a shell. `rm -r` of `/`, `~`, or `$HOME`. Git aliases that expand to any of these. A missing, blank, or non-string command.
  - **Ask:** a normal `git push` and any `curl`/`wget`.
  - **Allowed:** for example `git pull`, `git pull --no-rebase`, `git reset HEAD`, and `git reset --soft`. A `-f` inside a branch name (`my-feature`) is not a flag, and `curl -fsSL` in a separate command after `;`/`&&`/`|` is not a force-push.
  - **Fail closed:** invalid JSON or a crash prints a deny and exits 2, which Cursor treats as a deny even without `failClosed`.
  - **Matcher:** deliberately broad (`git|twine|publish|gh|curl|wget|rm`), so every denied form reaches the script.
  - Do not loosen this to make a task easier.
- When you learn something durable, propose an edit to this file or a skill in the same PR.

## Directory map

- `graph_guard/` — package: SQLite triples, extraction, PPR, hybrid retriever, guards; Tier B RDF/OWL/SHACL/SPARQL (`ontology_data/`, `rdf_export.py`, `reasoning.py`, `fuseki.py`)
- `tests/` — pytest. Default run skips only the opt-in Fuseki live test
- `eval/` — `real_sessions_ab.py` (honest labels), `real_vault_lift.py` + `results.json` (circular contrast), `sparql_vs_ppr.py`
- `examples/` — `run_sample.py` and a 7-note vault; no API key
- `docs/` — TRADEOFFS, the two eval writeups, SPARQL-vs-PPR, design specs
- `scripts/` — `run-fuseki.sh` (opt-in Java server), `check_receipts.py`
- `.github/` — CI (test, coverage comment, receipts, employer scan), CodeQL, Dependabot. Actions are SHA-pinned
- `.cursor/` — rules, hooks, Bugbot, MCP, `skills/verify-receipts/`

## Known traps

- **KG cache staleness.** The store keeps `corpus_fingerprint` in `meta` and rebuilds when the corpus changes. Do **not** reintroduce an `edges == 0` freshness test: one stale edge blocked rebuild forever, and `GraphRetriever` falls back to lexical when a query has no anchor, so a 2-node graph still looked plausible. Call `service.graph_health(retriever)` before attributing a result to the graph.
- **Two different session-number pairs exist in history.** An older note cited flat 0.6904 vs ensemble+PPR 0.6537. The published README table (0.6731 vs 0.6437) is the one to quote. Do not restate the older pair as the headline.
- **Ontology layer.** It ties the plain graph on retrieval. It earns its cost on fidelity, SHACL validation, entailment, and standards interop, not on retrieval lift.
- **`.coverage` is not source.** It was committed once; it is gitignored now. Do not add it back.
- **MCP.** `.cursor/mcp.json` points at Context7 (`CONTEXT7_API_KEY`) and agent-gate (`uvx`). Keys stay in the environment. Neither server is required to run tests.
