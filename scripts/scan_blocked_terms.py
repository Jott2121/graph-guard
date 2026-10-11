#!/usr/bin/env python3
"""Fail if any tracked file contains a blocked term (the owner's employer name).

The repo never stores the terms themselves. ``.github/blocked-terms.sha256``
holds one SHA-256 hex digest per line of a lowercased term, words joined by a
single space. The scanner lowercases each file, splits it into ``[a-z0-9]+``
words, and hashes every word and every phrase of up to ``MAX_WORDS`` words
(phrases may span a line break). Any digest match fails the run.

Extra terms can come from the ``BLOCKED_TERMS`` env var (comma-separated,
e.g. a CI secret). They are hashed the same way and never printed.

Exit codes: 0 clean, 1 blocked term found, 2 the scan could not run (missing,
empty, or malformed hash file; git failure; unreadable file). Anything other
than 0 must fail the gate.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

MAX_WORDS = 2
WORD = re.compile(r"[a-z0-9]+")
DIGEST = re.compile(r"[0-9a-f]{64}")
# Generated junk only. Data folders (results/, eval/, fixtures) stay in scope.
EXCLUDED_DIRS = {".git", "node_modules", "build", "dist", "__pycache__", ".venv", "venv"}


class ScanError(Exception):
    """The scan could not run; callers must treat this as a failure."""


def digest(term: str) -> str:
    return hashlib.sha256(" ".join(WORD.findall(term.lower())).encode()).hexdigest()


def load_digests(hash_file: Path, env_terms: str | None) -> tuple[set[str], int]:
    """Return (digests, longest phrase length in words)."""
    try:
        lines = hash_file.read_text().splitlines()
    except OSError as exc:
        raise ScanError(f"cannot read hash file {hash_file}: {exc}") from exc
    digests: set[str] = set()
    for number, raw in enumerate(lines, 1):
        line = raw.split("#", 1)[0].strip().lower()
        if not line:
            continue
        if not DIGEST.fullmatch(line):
            raise ScanError(f"{hash_file}:{number}: not a SHA-256 hex digest")
        digests.add(line)
    if not digests:
        raise ScanError(f"hash file {hash_file} has no digests")
    max_words = MAX_WORDS
    for term in (env_terms or "").split(","):
        words = WORD.findall(term.lower())
        if words:
            digests.add(digest(term))
            max_words = max(max_words, len(words))
    return digests, max_words


def tracked_files(root: Path) -> list[Path]:
    try:
        proc = subprocess.run(
            ["git", "ls-files", "-z"], cwd=root, capture_output=True, check=False
        )
    except OSError as exc:
        raise ScanError(f"git ls-files failed to start: {exc}") from exc
    if proc.returncode != 0:
        raise ScanError(f"git ls-files exited {proc.returncode}: {proc.stderr.decode(errors='replace')}")
    names = [n for n in proc.stdout.decode().split("\0") if n]
    if not names:
        raise ScanError("git ls-files returned no files")
    return [root / n for n in names if not EXCLUDED_DIRS.intersection(Path(n).parts[:-1])]


def scan_text(text: str, digests: set[str], max_words: int) -> list[tuple[int, str]]:
    """Return (line number, digest prefix) for every blocked word or phrase."""
    tokens: list[tuple[str, int]] = []
    for number, line in enumerate(text.lower().splitlines(), 1):
        tokens.extend((word, number) for word in WORD.findall(line))
    hits: list[tuple[int, str]] = []
    for start in range(len(tokens)):
        for size in range(1, max_words + 1):
            window = tokens[start : start + size]
            if len(window) < size:
                break
            h = hashlib.sha256(" ".join(w for w, _ in window).encode()).hexdigest()
            if h in digests:
                hits.append((window[0][1], h[:12]))
    return hits


def scan_file(path: Path, digests: set[str], max_words: int) -> list[tuple[int, str]]:
    if path.is_symlink() or not path.exists():
        return []
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ScanError(f"cannot read {path}: {exc}") from exc
    if b"\0" in data[:8192]:
        return []
    return scan_text(data.decode("utf-8", errors="replace"), digests, max_words)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*", type=Path, help="files to scan (default: all tracked files)")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repo root (default: cwd)")
    parser.add_argument("--hash-file", type=Path, default=None)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    hash_file = args.hash_file or root / ".github" / "blocked-terms.sha256"
    try:
        digests, max_words = load_digests(hash_file, os.environ.get("BLOCKED_TERMS"))
        files = args.paths or tracked_files(root)
        found = 0
        for path in files:
            for line, prefix in scan_file(path, digests, max_words):
                shown = path.relative_to(root) if path.is_relative_to(root) else path
                print(f"{shown}:{line}: blocked term (sha256 {prefix}...)")
                found += 1
    except ScanError as exc:
        print(f"blocked-term scan could not run: {exc}", file=sys.stderr)
        return 2
    if found:
        print(f"{found} blocked term hit(s); remove them before merging", file=sys.stderr)
        return 1
    print(f"blocked-term scan clean: {len(files)} file(s), {len(digests)} term digest(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
