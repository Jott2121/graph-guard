#!/usr/bin/env python3
"""Fail if any tracked file contains a blocked term (the owner's employer name).

The repo never stores the terms themselves. ``.github/blocked-terms.sha256``
holds one SHA-256 hex digest per line of a lowercased term, words joined by a
single space. The scanner lowercases each file, splits it into ``[a-z0-9]+``
words, and hashes every word and every 2-word phrase (phrases may span a line
break). Any digest match fails the run. This base check needs no secret.

``EMPLOYER_MARKERS`` (optional, e.g. an Actions secret of the same name) is an
extra case-insensitive regex alternation checked line by line. It adds to the
hash list; it never replaces it. Matches are reported without the matched text.

Exit codes: 0 clean, 1 blocked term found, 2 the scan could not run (missing,
empty, or malformed hash file; invalid EMPLOYER_MARKERS regex; git failure;
unreadable file). Anything other than 0 must fail the gate.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

HASH_FILE = Path(".github") / "blocked-terms.sha256"
MAX_WORDS = 2
WORD = re.compile(r"[a-z0-9]+")
DIGEST = re.compile(r"[0-9a-f]{64}")
# Generated junk only. Data folders (results/, eval/, fixtures) stay in scope.
EXCLUDED_DIRS = {".git", "node_modules", "build", "dist", "__pycache__", ".venv", "venv"}


class ScanError(Exception):
    """The scan could not run; callers must treat this as a failure."""


def digest(term: str) -> str:
    return hashlib.sha256(" ".join(WORD.findall(term.lower())).encode()).hexdigest()


def load_digests(hash_file: Path) -> set[str]:
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
    return digests


def load_markers(raw: str | None) -> re.Pattern[str] | None:
    if raw is None or not raw.strip():
        return None
    try:
        pattern = re.compile(raw.strip(), re.IGNORECASE)
    except re.error as exc:
        raise ScanError(f"EMPLOYER_MARKERS is not a valid regex: {exc}") from exc
    if pattern.search(""):
        raise ScanError("EMPLOYER_MARKERS matches the empty string (stray '|'?)")
    return pattern


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
    return [
        root / n
        for n in names
        if Path(n) != HASH_FILE and not EXCLUDED_DIRS.intersection(Path(n).parts[:-1])
    ]


def scan_text(text: str, digests: set[str], markers: re.Pattern[str] | None = None) -> list[tuple[int, str]]:
    """Return (line number, label) for every blocked word, phrase, or marker match."""
    tokens: list[tuple[str, int]] = []
    hits: list[tuple[int, str]] = []
    for number, line in enumerate(text.lower().splitlines(), 1):
        tokens.extend((word, number) for word in WORD.findall(line))
        if markers is not None and markers.search(line):
            hits.append((number, "EMPLOYER_MARKERS match"))
    for start in range(len(tokens)):
        for size in range(1, MAX_WORDS + 1):
            window = tokens[start : start + size]
            if len(window) < size:
                break
            h = hashlib.sha256(" ".join(w for w, _ in window).encode()).hexdigest()
            if h in digests:
                hits.append((window[0][1], f"sha256 {h[:12]}..."))
    return sorted(hits)


def scan_file(path: Path, digests: set[str], markers: re.Pattern[str] | None = None) -> list[tuple[int, str]]:
    if path.is_symlink() or not path.exists():
        return []
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ScanError(f"cannot read {path}: {exc}") from exc
    if b"\0" in data[:8192]:
        return []
    return scan_text(data.decode("utf-8", errors="replace"), digests, markers)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*", type=Path, help="files to scan (default: all tracked files)")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repo root (default: cwd)")
    parser.add_argument("--hash-file", type=Path, default=None)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    hash_file = args.hash_file or root / HASH_FILE
    try:
        digests = load_digests(hash_file)
        markers = load_markers(os.environ.get("EMPLOYER_MARKERS"))
        files = args.paths or tracked_files(root)
        found = 0
        for path in files:
            for line, label in scan_file(path, digests, markers):
                shown = path.relative_to(root) if path.is_relative_to(root) else path
                print(f"{shown}:{line}: blocked term ({label})")
                found += 1
    except ScanError as exc:
        print(f"blocked-term scan could not run: {exc}", file=sys.stderr)
        return 2
    if found:
        print(f"{found} blocked term hit(s); remove them before merging", file=sys.stderr)
        return 1
    extra = " + EMPLOYER_MARKERS" if markers else ""
    print(f"blocked-term scan clean: {len(files)} file(s), {len(digests)} term digest(s){extra}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
