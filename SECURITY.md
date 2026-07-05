# Security Policy

## Supported versions

`graph-guard` is actively maintained. Security fixes target the latest released
version on the `main` branch.

| Version          | Supported |
| ---------------- | --------- |
| latest (`main`)  | ✅        |
| older tags       | ❌        |

## Reporting a vulnerability

Please **do not** open a public issue for security vulnerabilities.

Report privately through GitHub's
[**Report a vulnerability**](https://github.com/Jott2121/graph-guard/security/advisories/new)
flow (the repository's **Security → Advisories** tab). I aim to acknowledge
reports within 72 hours and to ship a fix or mitigation for confirmed issues as
quickly as is practical.

When reporting, please include:

- a description of the issue and its impact,
- steps to reproduce (a minimal proof-of-concept if possible), and
- any suggested remediation.

## Scope

`graph-guard` builds a typed knowledge graph over a local note vault and exports
it to RDF/OWL/SHACL/SPARQL. Findings of particular interest:

- **Private-data leakage** past the eval harness's aggregate-only guarantee —
  `eval/results.json` and the retrieval-lift docs must never contain note ids,
  file paths, or query/gold text (enforced by a leak-check test).
- **Grounding or structural-refuse bypass** in the guards
  (`graph_guard/guards.py`).
- **Unsafe deserialization** when parsing untrusted RDF/Turtle, or **SPARQL
  injection** via unsanitized query terms (IRIs are serialized through rdflib's
  N3 form for this reason).
- **Supply-chain risk in CI** — this repository pins its GitHub Actions to commit
  SHAs and runs CodeQL + Dependabot, and pulls its `guarded-rag` dependency from
  a Git source (`github.com/Jott2121/rag-guard`).

Thanks for helping keep it solid.
