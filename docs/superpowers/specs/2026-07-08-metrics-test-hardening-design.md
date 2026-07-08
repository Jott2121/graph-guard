# Spec — Harden the eval-metrics tests (test the tests)

**Date:** 2026-07-08 · **Status:** approved, in build · **Branch:** `feat/metrics-test-hardening`
**Target:** `graph_guard/eval_metrics.py` (the code that produces the Gate D hit@k / MRR lift numbers)

## Goal
Add a quality layer on top of the existing 8 example-based tests in `tests/test_eval_metrics.py`
so that a false-pass test cannot silently hide a bug in the metric math. This is Phase 1 of 2:
prove the pattern on one module; Phase 2 (extract a reusable harness) is a separate cycle.

## Honest scope
This *reduces* the chance of false-pass / bugged tests; it does not make tests provably perfect.
Some mutants are equivalent (unkillable) and that is expected, not a failure.

## The three pillars
1. **Property-based tests (Hypothesis)** — state invariants that must always hold and let the tool
   generate hundreds of adversarial inputs:
   - every `hit@k` and `mrr` is in `[0.0, 1.0]` (or `None` when guarded off for `N > k`)
   - monotonicity: `hit@1 <= hit@5 <= hit@10` (where all are defined)
   - a perfect arm (gold always rank 1) → all scores `1.0`; gold never present → all `0.0`
   - `n` equals the number of probes in the family
2. **Metamorphic tests** — relations that must hold when there is no single "right answer":
   - reordering the probes must not change the aggregate metrics
   - `lift(A, B) == -lift(B, A)` for every numeric metric
   - `lift(A, A) == 0` for every numeric metric
3. **Mutation testing (mutmut)** — deliberately break `eval_metrics.py` and confirm the tests catch
   it. Baseline the *current* suite, then re-run after adding pillars 1–2 and drive survivors down.

## Method
1. Branch; add `hypothesis` + `mutmut` to the `dev` extra; verify both run on Python 3.14.
2. Baseline mutation run on the current tests — record the surviving mutants.
3. Add property tests, then metamorphic tests, in `tests/test_eval_metrics_properties.py`.
4. Re-run mutation; investigate each survivor: real gap (add a test / fix code) vs equivalent (note it).
5. Commit to the local branch. Recap + Codespeak lesson. Pushing to the public repo is a separate gate.

## Files
- new: `tests/test_eval_metrics_properties.py`
- edit: `pyproject.toml` (dev extra: `+ hypothesis`, `+ mutmut`)
- keep: `tests/test_eval_metrics.py` (untouched — we add, never replace)
- edit (only if a mutant exposes a real bug): `graph_guard/eval_metrics.py`

## Success criteria
- Property + metamorphic tests pass and are themselves able to fail (verified by mutation).
- Mutation survivors are either killed or explicitly explained as equivalent.
- No change to `eval_metrics.py` unless a mutant proves a real bug; if one is found, it is fixed and
  the numbers are re-verified.
