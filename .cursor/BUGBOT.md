# .cursor/BUGBOT.md — review rules for graph-guard
# (Bugbot does NOT read .cursor/rules/*.mdc; it reads this file.)

Flag as **blocking**:
1. Any guard, gate, validator, or refusal path that now fails OPEN (returns allow/True/answer on exception, timeout, empty, or malformed input). This includes `service.graph_health` and the session-eval ABORT paths.
2. Lowered thresholds: `--cov-fail-under` (floor is 90), mutation score floors, or retry/timeout bounds removed.
3. Tests that were deleted, skipped, xfailed, or had assertions weakened without a stated reason in the PR body. The only allowed default skip is the opt-in Fuseki live test.
4. README or docs numbers that changed without a reproducing command or artifact in the PR, or a `scripts/check_receipts.py` update in the same PR. Restating the structure-derived +14%/+26% figures as the headline, or calling them an upper bound, is a blocking claim error.
5. Any content that looks like employer or corporate data: an employer's name or abbreviation, its programs, products, or sites, internal acronyms, CUI/ITAR markings, real-looking employee records, internal URLs. This repo is personal work only. The README author byline does not name an employer; do not add one.
6. A freshness check that treats the KG as fresh whenever `edges != 0`. Rebuild is keyed on `corpus_fingerprint`.
7. Secrets, tokens, `.env` files, `.coverage`, or absolute personal paths committed.
8. Unpinned GitHub Actions (must be full SHA) or widened workflow `permissions:`.
9. Live network or model calls added to the default test path. `GRAPH_GUARD_FUSEKI_LIVE` stays opt-in.

Flag as **non-blocking**:
- New runtime dependency without justification.
- Non-deterministic code in eval paths (unseeded RNG, unordered iteration in hashes or output).
- Exceptions swallowed in non-decision code.

Do not comment on: formatting nitpicks; naming bikesheds. This repo does not run ruff in CI.
