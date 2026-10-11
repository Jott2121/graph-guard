"""Regression tests for the agent guards Bugbot flagged on the setup PR.

The employer scan must fail the step when a banned term is committed.
The shell hook must emit parseable JSON when the command contains quotes.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / ".cursor" / "hooks" / "guard-shell.sh"
CI = ROOT / ".github" / "workflows" / "ci.yml"
# Split so this source file does not itself contain the banned term.
# git grep scans tracked files, and this test is one of them.
BANNED = "lock" + "heed"


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


def _run_scan(cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-eo", "pipefail", "-c", _employer_scan_script()],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


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


def test_employer_scan_fails_closed_on_a_banned_term(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "note.txt").write_text(f"see {BANNED}\n")
    subprocess.run(["git", "add", "note.txt"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=test@example.com", "-c", "user.name=test", "commit", "-qm", "init"],
        cwd=repo,
        check=True,
    )
    proc = _run_scan(repo)
    assert proc.returncode != 0
    assert BANNED in (proc.stdout + proc.stderr).lower()


def test_pull_matcher_sees_plain_and_rebasing_pulls():
    hooks = json.loads((ROOT / ".cursor" / "hooks.json").read_text())
    matcher = hooks["hooks"]["beforeShellExecution"][0]["matcher"]
    assert re.search(matcher, "git pull")
    assert re.search(matcher, "git pull --rebase origin main")
    assert not re.search(matcher, "git status")


def test_plain_pull_is_allowed_and_rebasing_pull_is_denied():
    assert _run_guard("git pull")["permission"] == "allow"
    assert _run_guard("git pull origin main")["permission"] == "allow"
    assert _run_guard("git pull --rebase origin main")["permission"] == "deny"


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
