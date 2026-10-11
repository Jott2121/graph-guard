"""Regression tests for the agent guards Bugbot flagged on the setup PR.

The employer scan must fail the step when a banned term is committed. Employer
names come only from EMPLOYER_MARKERS, so these tests use a synthetic marker.
The shell hook must emit parseable JSON when the command contains quotes.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / ".cursor" / "hooks" / "guard-shell.sh"
SCAN_HOOK = ROOT / ".cursor" / "hooks" / "format-and-scan.sh"
CI = ROOT / ".github" / "workflows" / "ci.yml"
# Synthetic stand-in for a real employer name; never put a real one here.
MARKER = "zq-" + "acme-widgets"
# Split so this source file does not itself trip the generic scan.
# git grep scans tracked files, and this test is one of them.
GENERIC = "IT" + "AR"


def _employer_scan_script() -> str:
    text = CI.read_text()
    marker = "name: Block employer / export-control markers and committed build junk\n"
    run_at = text.index("run: |", text.index(marker))
    body = []
    for line in text[run_at:].splitlines()[1:]:
        if line.startswith("          "):
            body.append(line[10:])
        elif line.strip() == "":
            body.append("")
        else:
            break
    script = "\n".join(body).strip()
    commands = [line.strip() for line in script.splitlines() if line.strip() and not line.strip().startswith("#")]
    assert any(line.startswith("git grep") for line in commands)
    assert not any(line.startswith("!") for line in commands)
    return script


def _env(markers: str | None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k != "EMPLOYER_MARKERS"}
    if markers is not None:
        env["EMPLOYER_MARKERS"] = markers
    return env


def _run_scan(cwd: Path, markers: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-eo", "pipefail", "-c", _employer_scan_script()],
        cwd=cwd,
        env=_env(markers),
        capture_output=True,
        text=True,
        check=False,
    )


def _repo_with(tmp_path: Path, text: str) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "note.txt").write_text(text)
    subprocess.run(["git", "add", "note.txt"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=test@example.com", "-c", "user.name=test", "commit", "-qm", "init"],
        cwd=repo,
        check=True,
    )
    return repo


def _run_scan_hook(tmp_path: Path, text: str, markers: str | None) -> bool:
    """Run the afterFileEdit scanner on a file; return True if it logged a warning."""
    target = tmp_path / "edited.txt"
    target.write_text(text)
    proc = subprocess.run(
        ["bash", str(SCAN_HOOK)],
        input=json.dumps({"file_path": str(target)}),
        cwd=tmp_path,
        env=_env(markers),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return (tmp_path / ".cursor" / "hook-logs" / "warnings.log").exists()


def _run_guard_raw(payload: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(GUARD)],
        input=payload,
        capture_output=True,
        text=True,
        check=False,
    )


def _decision(payload: str) -> dict:
    proc = _run_guard_raw(payload)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _run_guard(command: str) -> dict:
    return _decision(json.dumps({"command": command}))


def test_employer_scan_passes_on_this_tree():
    proc = _run_scan(ROOT)
    assert proc.returncode == 0, proc.stdout + proc.stderr


@pytest.mark.parametrize("markers", [MARKER, f"other-name\n{MARKER}\n", f"\\b{MARKER}\\b"])
def test_employer_scan_fails_closed_on_a_marker_from_the_env(tmp_path, markers):
    proc = _run_scan(_repo_with(tmp_path, f"see {MARKER.upper()}\n"), markers)
    assert proc.returncode != 0
    assert MARKER in (proc.stdout + proc.stderr).lower()


@pytest.mark.parametrize("markers", [None, "", "\n", " \n \t\n"])
def test_employer_scan_runs_generic_patterns_without_markers(tmp_path, markers):
    proc = _run_scan(_repo_with(tmp_path, f"{GENERIC} controlled\n"), markers)
    assert proc.returncode != 0
    assert proc.stdout.strip()


@pytest.mark.parametrize("markers", [None, "", "\n", " \n \t\n", f"{MARKER}\n\n", f"{MARKER}\n  \nother\r\n"])
def test_blank_marker_lines_do_not_match_everything(tmp_path, markers):
    proc = _run_scan(_repo_with(tmp_path, "an ordinary synthetic note\n"), markers)
    assert proc.returncode == 0, proc.stdout + proc.stderr


@pytest.mark.parametrize("markers", ["|", f"{MARKER}||other", f"({MARKER})?"])
def test_employer_scan_rejects_markers_that_match_everything(tmp_path, markers):
    proc = _run_scan(_repo_with(tmp_path, "an ordinary synthetic note\n"), markers)
    assert proc.returncode != 0
    assert "EMPLOYER_MARKERS" in proc.stderr


def test_edit_hook_warns_on_a_marker_from_the_env(tmp_path):
    assert _run_scan_hook(tmp_path, f"see {MARKER}\n", f"{MARKER}\n")


def test_edit_hook_runs_generic_patterns_without_markers(tmp_path):
    assert _run_scan_hook(tmp_path, f"{GENERIC} controlled\n", None)


@pytest.mark.parametrize("markers", [None, "", "\n", " \n \t\n", f"{MARKER}\n  \n"])
def test_edit_hook_ignores_clean_files_with_blank_markers(tmp_path, markers):
    assert not _run_scan_hook(tmp_path, "an ordinary synthetic note\n", markers)


def test_edit_hook_drops_markers_that_match_everything(tmp_path):
    assert _run_scan_hook(tmp_path, "an ordinary synthetic note\n", f"{MARKER}||other")
    log = (tmp_path / ".cursor" / "hook-logs" / "warnings.log").read_text()
    assert "EMPLOYER_MARKERS matches an empty line" in log
    assert "pattern in" not in log


def test_pull_matcher_sees_plain_and_rebasing_pulls():
    hooks = json.loads((ROOT / ".cursor" / "hooks.json").read_text())
    matcher = hooks["hooks"]["beforeShellExecution"][0]["matcher"]
    assert re.search(matcher, "git pull")
    assert re.search(matcher, "git pull --rebase origin main")
    assert re.search(matcher, "git -C repo pull --rebase")
    # The matcher is broad on purpose (any `git`), so harmless git commands
    # reach the guard and must come back allowed.
    assert _run_guard("git status")["permission"] == "allow"


def test_plain_pull_is_allowed_and_rebasing_pull_is_denied():
    assert _run_guard("git pull")["permission"] == "allow"
    assert _run_guard("git pull origin main")["permission"] == "allow"
    assert _run_guard("git pull --rebase origin main")["permission"] == "deny"
    assert _run_guard("git pull -r")["permission"] == "deny"
    assert _run_guard("git pull origin -r")["permission"] == "deny"
    assert _run_guard("git pull -ur origin")["permission"] == "deny"
    assert _run_guard("git pull -r; echo done")["permission"] == "deny"
    assert _run_guard("git pull origin -r | cat")["permission"] == "deny"
    assert _run_guard("git pull -r && true")["permission"] == "deny"
    assert _run_guard("echo done; git pull")["permission"] == "allow"


def test_missing_blank_and_non_string_commands_are_denied():
    payloads = [
        "{}",
        json.dumps({"cwd": "/tmp"}),
        json.dumps({"command": ""}),
        json.dumps({"command": "   \n\t"}),
        json.dumps({"command": None}),
        json.dumps({"command": 1}),
        json.dumps({"command": ["git", "status"]}),
        json.dumps({"command": {"cmd": "git status"}}),
        "[]",
    ]
    for payload in payloads:
        decision = _decision(payload)
        assert decision["permission"] == "deny", payload


def test_invalid_json_exits_nonzero():
    for payload in ("{", "", "not-json", '{"command":'):
        proc = _run_guard_raw(payload)
        assert proc.returncode != 0, payload
        assert "allow" not in proc.stdout


def test_ask_json_roundtrips_when_the_command_has_quotes():
    command = 'curl -fsSL "https://example.com/a?q=\\"x\\""'
    out = _run_guard(command)
    assert out["permission"] == "ask"
    assert command in out["user_message"]


def test_force_push_is_denied_and_plain_push_asks():
    assert _run_guard("git push --force")["permission"] == "deny"
    asked = _run_guard("git push -u origin cursor/agent-setup-b6c5")
    assert asked["permission"] == "ask"
    assert _run_guard("git status")["permission"] == "allow"


def test_rewrite_flags_are_denied_away_from_the_subcommand():
    denied = (
        "git push origin --force",
        "git push origin -f",
        "git push -u origin --force",
        "git push origin --force-with-lease",
        "git push origin -uf",
        "git push -fu origin",
        "git push origin -uf; git status",
        "git push origin -uf | cat",
        "git push -fu origin && true",
        "git reset HEAD --hard",
        "git reset --hard HEAD",
        "git reset HEAD --hard; true",
    )
    for command in denied:
        assert _run_guard(command)["permission"] == "deny", command
    assert _run_guard("git reset HEAD")["permission"] == "allow"
    assert _run_guard("git commit -f")["permission"] == "allow"
    asked = _run_guard("git push -u origin main; git status")
    assert asked["permission"] == "ask"
