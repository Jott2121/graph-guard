---
name: verify-receipts
description: Use before opening or updating a PR, or when README/docs numbers change. Re-runs this repo's tests and receipt check, cross-checks published numbers, and writes a receipts block for the PR body.
---
# Verify receipts

1. Read AGENTS.md "Commands". From a clean install, run:
   - `pip install -e ".[dev,rdf]"`
   - `python -m pytest -q --cov=graph_guard --cov-report=term-missing --cov-fail-under=90`
   - `python scripts/check_receipts.py`
   - `python examples/run_sample.py`
   Lint and typecheck are not configured. Do not claim they passed.
   Do **not** run `eval/real_sessions_ab.py` or `eval/real_vault_lift.py` unless a local vault is actually present. Never pass `--skip-controls`. If you did not run the session eval, mark those README figures as locked-not-recomputed.
2. `git diff origin/main -- README.md docs/ eval/results.json scripts/check_receipts.py` — list every number that changed. For each figure that comes from `eval/results.json`, re-run `python scripts/check_receipts.py`. If a number changed and you cannot show the artifact, mark it UNVERIFIED and stop.
3. Grep the diff for employer-data and secret patterns (see `.cursor/rules/40-security-and-data.mdc`): `lockheed`, `lmco`, `CUI`, `ITAR`, `EXPORT CONTROLLED`, `PROPRIETARY`, private keys. Any new hit outside `.cursor/` and `AGENTS.md` = stop and report. The README author byline does not name an employer.
4. Confirm `--cov-fail-under=90` is unchanged, no coverage floor was lowered, and no tests were skipped or removed. The Fuseki live test is the only opt-in skip.
5. Output a Markdown block:
   - Commands run + pass/fail
   - Numbers: before → after → command or artifact → reproduced? (Y/N)
   - Not verified / known gaps (session-eval table needs a private vault; badges say 137 / 97%)
6. Paste that block into the PR's "How verified" section. Never claim a check passed that you didn't run.
