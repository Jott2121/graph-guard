"""The hashed employer-name scanner catches planted terms and fails closed.

Planted terms are built from fragments at runtime and written only to temp
repos, so no blocked term is ever committed (the scanner checks this file too).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCANNER = ROOT / "scripts" / "scan_blocked_terms.py"
HASHES = ROOT / ".github" / "blocked-terms.sha256"
HOOK = ROOT / ".cursor" / "hooks" / "format-and-scan.sh"
PLANTED = "lock" + "heed"
PLANTED_ABBR = "l" + "mco"


def _scan(cwd: Path, *args: str, markers: str | None = None) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k != "EMPLOYER_MARKERS"}
    if markers is not None:
        env["EMPLOYER_MARKERS"] = markers
    return subprocess.run(
        [sys.executable, str(SCANNER), *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _repo(tmp_path: Path, files: dict[str, str], hashes: str | None = None) -> Path:
    repo = tmp_path / "repo"
    (repo / ".github").mkdir(parents=True)
    if hashes is None:
        shutil.copy(HASHES, repo / ".github" / "blocked-terms.sha256")
    else:
        (repo / ".github" / "blocked-terms.sha256").write_text(hashes)
    for name, text in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    return repo


def test_clean_tree_passes():
    proc = _scan(ROOT)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "blocked-term scan clean" in proc.stdout


def test_hash_file_is_committed_and_not_plaintext():
    text = HASHES.read_text().lower()
    assert PLANTED not in text and PLANTED_ABBR not in text
    digests = [line for line in text.splitlines() if line and not line.startswith("#")]
    assert len(digests) >= 1


def test_planted_term_is_caught_in_a_data_folder_without_echoing_it(tmp_path):
    repo = _repo(tmp_path, {"results/run.json": f'{{"note": "from {PLANTED.title()} Corp"}}\n', "ok.md": "clean\n"})
    proc = _scan(repo)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "results/run.json:1: blocked term" in proc.stdout
    assert "ok.md" not in proc.stdout
    assert PLANTED not in (proc.stdout + proc.stderr).lower()


def test_planted_abbreviation_is_caught_as_a_whole_word_only(tmp_path):
    repo = _repo(tmp_path, {"a.md": f"x\n{PLANTED_ABBR.upper()}-internal\n", "b.md": f"un{PLANTED_ABBR}ed llm lms\n"})
    proc = _scan(repo)
    assert proc.returncode == 1
    assert "a.md:2: blocked term" in proc.stdout
    assert "b.md" not in proc.stdout


def test_planted_term_is_caught_with_no_secret_set(tmp_path):
    repo = _repo(tmp_path, {"AGENTS.md": f"Never use {PLANTED} data\n"})
    proc = _scan(repo)
    assert proc.returncode == 1
    proc = _scan(repo, markers="")
    assert proc.returncode == 1


def test_employer_markers_regex_adds_terms_without_echoing_them(tmp_path):
    repo = _repo(tmp_path, {"notes.md": "we met\nAcme Widgets today\n", "other.md": "acme alone\n"})
    assert _scan(repo).returncode == 0
    proc = _scan(repo, markers=r"acme\s+widgets|globex")
    assert proc.returncode == 1
    assert "notes.md:2: blocked term (EMPLOYER_MARKERS match)" in proc.stdout
    assert "other.md" not in proc.stdout
    assert "widgets" not in proc.stdout.lower()


def test_employer_markers_does_not_replace_the_hash_list(tmp_path):
    repo = _repo(tmp_path, {"a.md": f"{PLANTED}\n"})
    assert _scan(repo, markers="globex").returncode == 1


def test_invalid_or_empty_matching_markers_fail_closed(tmp_path):
    repo = _repo(tmp_path, {"a.md": "clean\n"})
    for bad in ("acme(", "acme|", ".*"):
        proc = _scan(repo, markers=bad)
        assert proc.returncode == 2, bad
        assert "EMPLOYER_MARKERS" in proc.stderr


def test_hash_file_itself_is_excluded(tmp_path):
    repo = _repo(tmp_path, {"a.md": "clean\n"})
    (repo / ".github" / "blocked-terms.sha256").write_text(f"{'0' * 64}\n# globex\n")
    assert _scan(repo, markers="globex").returncode == 0


def test_explicit_path_mode_scans_only_that_file(tmp_path):
    repo = _repo(tmp_path, {"bad.md": f"{PLANTED}\n", "good.md": "fine\n"})
    assert _scan(repo, "good.md").returncode == 0
    assert _scan(repo, "bad.md").returncode == 1


def test_symlink_target_is_scanned(tmp_path):
    repo = _repo(tmp_path, {"a.md": "clean\n"})
    (repo / "link").symlink_to(f"docs/{PLANTED}-notes.md")
    subprocess.run(["git", "add", "link"], cwd=repo, check=True)
    proc = _scan(repo)
    assert proc.returncode == 1
    assert "link:1: blocked term" in proc.stdout


def test_binary_file_is_scanned(tmp_path):
    repo = _repo(tmp_path, {"a.md": "clean\n"})
    (repo / "blob.bin").write_bytes(b"\x00\x01\xff " + PLANTED.encode() + b" \x00")
    subprocess.run(["git", "add", "blob.bin"], cwd=repo, check=True)
    assert _scan(repo).returncode == 1


def test_missing_or_unreadable_file_fails_closed(tmp_path):
    repo = _repo(tmp_path, {"a.md": "clean\n", "gone.md": "clean\n"})
    (repo / "gone.md").unlink()
    proc = _scan(repo)
    assert proc.returncode == 2
    assert "gone.md" in proc.stderr
    assert _scan(repo, "nope.md").returncode == 2


def test_missing_hash_file_fails_closed(tmp_path):
    repo = _repo(tmp_path, {"a.md": "clean\n"})
    (repo / ".github" / "blocked-terms.sha256").unlink()
    proc = _scan(repo)
    assert proc.returncode == 2
    assert "could not run" in proc.stderr


def test_empty_or_comment_only_hash_file_fails_closed(tmp_path):
    for content in ("", "\n\n", "# nothing here\n"):
        repo = _repo(tmp_path, {"a.md": "clean\n"}, hashes=content)
        proc = _scan(repo, markers="acme")
        assert proc.returncode == 2, repr(content)
        shutil.rmtree(repo)


def test_malformed_hash_file_fails_closed(tmp_path):
    repo = _repo(tmp_path, {"a.md": "clean\n"}, hashes=f"{PLANTED}\n")
    assert _scan(repo).returncode == 2


def test_outside_a_git_repo_fails_closed(tmp_path):
    (tmp_path / ".github").mkdir()
    shutil.copy(HASHES, tmp_path / ".github" / "blocked-terms.sha256")
    env = {**os.environ, "GIT_CEILING_DIRECTORIES": str(tmp_path.parent)}
    env.pop("EMPLOYER_MARKERS", None)
    proc = subprocess.run(
        [sys.executable, str(SCANNER)], cwd=tmp_path, env=env, capture_output=True, text=True, check=False
    )
    assert proc.returncode == 2


def test_generated_junk_is_skipped_but_dotfiles_and_policy_files_are_not(tmp_path):
    repo = _repo(
        tmp_path,
        {"node_modules/pkg/x.js": f"// {PLANTED}\n", "build/out.txt": f"{PLANTED}\n"},
    )
    assert _scan(repo).returncode == 0
    for name in (".cursor/rules/x.mdc", "AGENTS.md", ".github/workflows/ci.yml"):
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{PLANTED}\n")
        subprocess.run(["git", "add", name], cwd=repo, check=True)
        assert _scan(repo).returncode == 1, name
        path.unlink()
        subprocess.run(["git", "rm", "-q", "--cached", name], cwd=repo, check=True)


def test_ci_runs_the_scanner_with_the_optional_secret():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "run: python3 scripts/scan_blocked_terms.py" in ci
    assert "EMPLOYER_MARKERS: ${{ secrets.EMPLOYER_MARKERS }}" in ci
    assert "BLOCKED_TERMS" not in ci


def test_edit_hook_warns_on_a_planted_term(tmp_path):
    repo = _repo(tmp_path, {"clean.md": "fine\n", "bad.md": f"{PLANTED}\n"})
    (repo / "scripts").mkdir()
    shutil.copy(SCANNER, repo / "scripts" / SCANNER.name)
    log = repo / ".cursor" / "hook-logs" / "warnings.log"
    for name in ("clean.md", "bad.md"):
        proc = subprocess.run(
            ["bash", str(HOOK)],
            cwd=repo,
            input=json.dumps({"file_path": name}),
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr
    warnings = log.read_text()
    assert "bad.md" in warnings and "clean.md" not in warnings
