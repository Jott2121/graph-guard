#!/usr/bin/env python3
"""Cross-check published numbers against committed artifacts.

Recomputes the structure-derived contrast (hit@10 / MRR relative lift, owlrl
delta) from ``eval/results.json`` and requires the README and
``docs/EVAL-real-vault-lift.md`` to still show those figures.

The real-session headline has no public raw artifact (private vault). This
script locks the README strings for that table. It does not recompute them
and it does not change any published number.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Published snapshot. Changing these means the artifact and the docs changed
# together, and this file must be updated in that same PR.
VAULT = {"notes": 517, "nodes": 807, "edges": 1814}
PROBES = {"multi_hop": 159, "simple_lookup": 517}
FLAT_MULTI = {"hit@10": 0.3145, "mrr": 0.1303}
GRAPH_MULTI = {"hit@10": 0.3585, "mrr": 0.1647}
REASONED_HIT10 = 0.3585
REASONED_VS_GRAPH_MRR = 0.0008

SESSION_LOCK = (
    "0.6731",
    "0.6363",
    "0.6598",
    "0.6437",
    "0.2499",
    "25/25 (100%)",
    "tests-137",
    "coverage-97%25",
    "~97% coverage",
)


def _close(actual: float, expected: float) -> bool:
    return abs(actual - expected) < 1e-9


def main() -> int:
    errors: list[str] = []

    def need(ok: bool, message: str) -> None:
        if not ok:
            errors.append(message)

    results = json.loads((ROOT / "eval" / "results.json").read_text())
    readme = (ROOT / "README.md").read_text()
    eval_doc = (ROOT / "docs" / "EVAL-real-vault-lift.md").read_text()
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    gitignore = (ROOT / ".gitignore").read_text()
    sessions = (ROOT / "eval" / "real_sessions_ab.py").read_text()

    vault = results["vault"]
    probes = results["probes"]
    flat = results["arms"]["flat"]["multi_hop"]
    graph = results["arms"]["graph"]["multi_hop"]
    reasoned = results["arms"]["reasoned"]["multi_hop"]
    mrr_delta = results["lift"]["reasoned_vs_graph"]["multi_hop"]["mrr"]

    for key, expected in VAULT.items():
        need(vault[key] == expected, f"results.json vault.{key} is {vault[key]}, expected {expected}")
    for key, expected in PROBES.items():
        need(probes[key] == expected, f"results.json probes.{key} is {probes[key]}, expected {expected}")
    for key, expected in FLAT_MULTI.items():
        need(_close(flat[key], expected), f"results.json flat multi_hop {key} is {flat[key]}")
    for key, expected in GRAPH_MULTI.items():
        need(_close(graph[key], expected), f"results.json graph multi_hop {key} is {graph[key]}")
    need(_close(reasoned["hit@10"], REASONED_HIT10), f"reasoned hit@10 is {reasoned['hit@10']}")
    need(_close(mrr_delta, REASONED_VS_GRAPH_MRR), f"reasoned-vs-graph MRR delta is {mrr_delta}")

    rel_hit = round((graph["hit@10"] - flat["hit@10"]) / flat["hit@10"] * 100)
    rel_mrr = round((graph["mrr"] - flat["mrr"]) / flat["mrr"] * 100)
    need(rel_hit == 14, f"relative hit@10 rounds to {rel_hit}, expected 14")
    need(rel_mrr == 26, f"relative MRR rounds to {rel_mrr}, expected 26")

    for label, text in (("README.md", readme), ("docs/EVAL-real-vault-lift.md", eval_doc)):
        for needle in ("0.3145", "0.3585", "0.1303", "0.1647", "0.0008", "517", "807", "159"):
            need(needle in text, f"{label} is missing {needle}")
        need("1814" in text or "1,814" in text, f"{label} is missing the 1814 edge count")

    need("+14% rel" in readme, "README.md is missing '+14% rel'")
    need("+26% rel" in readme, "README.md is missing '+26% rel'")
    need("+14% relative" in eval_doc, "EVAL doc is missing '+14% relative'")
    need("+26% relative" in eval_doc, "EVAL doc is missing '+26% relative'")

    for needle in SESSION_LOCK:
        need(needle in readme, f"README.md is missing locked string {needle!r}")

    floors = [int(n) for n in re.findall(r"--cov-fail-under=(\d+)", ci)]
    need(floors == [90], f"CI coverage floors are {floors}, expected [90]")
    need("ABORT: controls failed" in sessions, "real_sessions_ab.py no longer aborts when controls fail")
    need("ABORT: the graph is empty" in sessions, "real_sessions_ab.py no longer aborts on an empty graph")
    need(re.search(r"(?m)^\.coverage$", gitignore) is not None, ".gitignore is missing .coverage")
    need(".cursor/hook-logs/" in gitignore, ".gitignore is missing .cursor/hook-logs/")

    tracked = subprocess.run(
        ["git", "ls-files", ".coverage"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    need(tracked.stdout.strip() == "", f".coverage is still tracked: {tracked.stdout.strip()}")

    print("receipts: structure-derived contrast matches eval/results.json")
    print(f"  multi-hop hit@10 {FLAT_MULTI['hit@10']} -> {GRAPH_MULTI['hit@10']} (+{rel_hit}% rel)")
    print(f"  multi-hop MRR {FLAT_MULTI['mrr']} -> {GRAPH_MULTI['mrr']} (+{rel_mrr}% rel)")
    print(f"  reasoned vs graph MRR delta {REASONED_VS_GRAPH_MRR}")
    print("receipts: session-eval headline is locked to README text, not recomputed")
    print("  private vault; no committed raw artifact. Do not use --skip-controls.")
    print("  published badges remain tests-137 and coverage-97%; CI floor is 90")
    if errors:
        print("receipts FAILED:", file=sys.stderr)
        for message in errors:
            print(f"  - {message}", file=sys.stderr)
        return 1
    print("receipts OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
