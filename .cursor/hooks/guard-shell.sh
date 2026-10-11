#!/usr/bin/env bash
# beforeShellExecution guard (canonical copy: see .cursor/hooks/README.md).
# Reads {"command": "...", "cwd": "..."} on stdin and prints one JSON decision.
#
# deny: force-push (-f, clustered -uf/-fu, --force*, +refspec, --mirror),
#       reset --hard, any rebase (git rebase, git pull --rebase / -r, pull.rebase
#       config), tags and publishing, pipe-to-shell, destructive rm of / or ~,
#       and a missing, blank, or non-string command.
# ask:  a normal git push, curl, wget.
#
# Flags are matched as whole arguments anywhere after the subcommand, after
# shell unquoting, so `git push origin "--force"` is a force-push and
# `git push origin my-feature` is not. Each simple command is judged on its own:
# `git push origin main && curl -fsSL URL` is a push plus a fetch, not a
# force-push. Quoted strings that look like commands (`sh -c '...'`, `$(...)`)
# are checked as commands too.
#
# Fails closed: invalid JSON, a crash, or a missing python3 exits non-zero, and
# exit 2 denies even without hooks.json "failClosed": true.
set -euo pipefail

read -r -d '' GUARD_PY <<'PY' || true
import json
import re
import shlex
import sys

FORCE_LONG = ("force", "force-with-lease", "force-if-includes", "mirror")
TAG_LONG = ("tags", "follow-tags")
FALSY = ("false", "no", "off", "0")
SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "ash", "fish"}
FETCHERS = {"curl", "wget"}
PUBLISHERS = {"uv", "poetry", "hatch", "flit", "npm", "pnpm", "yarn", "cargo"}
GIT_VALUED = {"-C", "-c", "--git-dir", "--work-tree", "--namespace",
              "--super-prefix", "--config-env"}
CONFIG_VALUED = {"-f", "--file", "--blob", "-t", "--type", "--default",
                 "--comment", "--value"}
FETCH_WORD = re.compile(r"(?<![\w.-])(?:curl|wget)(?![\w.-])")
RM_TARGETS = {"/", "/*", "~", "~/", "~/*", "$HOME", "$HOME/", "$HOME/*",
              "${HOME}", "${HOME}/", "${HOME}/*", "--no-preserve-root"}
SHELL_SUBST_FETCH = re.compile(
    r"(?:^|[^\w.-])(?:(?:ba|z|da|k|a)?sh|source|\.)\s[^;&|\n]*"
    r"(?:<\(|\$\(|`)\s*(?:\S*/)?(?:curl|wget)\b"
)

FORCE_MSG = "Force-push blocked by repo policy."
REWRITE_MSG = "History rewrite blocked by repo policy. This includes git pull --rebase."
PUBLISH_MSG = "Releases/publishing are human-only."
PIPE_MSG = "Pipe-to-shell blocked."
RM_MSG = "Destructive delete blocked."

ALLOW, ASK_NETWORK, ASK_PUSH = 0, 1, 2


class Denied(Exception):
    pass


def emit(permission, message=""):
    payload = {"permission": permission}
    if message:
        payload["user_message"] = message
    if permission == "deny":
        payload["agent_message"] = message + " Open a PR instead; a human will do this step."
    sys.stdout.write(json.dumps(payload) + "\n")


def basename(token):
    name = token.replace("\\", "/").rsplit("/", 1)[-1]
    return name[:-4] if name.lower().endswith(".exe") else name


def split_commands(text):
    """Split on unquoted control operators. Returns [(segment, op_after)]."""
    out, buf, quote, i, n = [], [], None, 0, len(text)

    def flush(op):
        seg = "".join(buf)
        buf.clear()
        if seg.strip():
            out.append((seg, op))
        elif op == "|" and out:
            # `(curl x) | sh`, `{ curl x; } | sh`: the group's output is piped.
            out[-1] = (out[-1][0], op)

    while i < n:
        c = text[i]
        if quote == "'":
            buf.append(c)
            quote = None if c == "'" else quote
            i += 1
            continue
        if quote == '"':
            buf.append(c)
            if c == "\\" and i + 1 < n:
                buf.append(text[i + 1])
                i += 2
                continue
            quote = None if c == '"' else quote
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            buf.append(" " if text[i + 1] == "\n" else c + text[i + 1])
            i += 2
            continue
        if c in "'\"":
            quote = c
            buf.append(c)
            i += 1
            continue
        if text.startswith(("&&", "||"), i):
            flush(";")
            i += 2
            continue
        if text.startswith("|&", i):
            flush("|")
            i += 2
            continue
        if c == "|":
            flush("|")
            i += 1
            continue
        if c == "&":
            # `2>&1`, `>&2`, `&>file` are redirections, not background operators.
            if (i and text[i - 1] in "<>") or text.startswith("&>", i):
                buf.append(c)
                i += 1
                continue
            flush(";")
            i += 1
            continue
        if text.startswith("$(", i):
            flush(";")
            i += 2
            continue
        if c in ";\n()`":
            flush(";")
            i += 1
            continue
        buf.append(c)
        i += 1
    flush(None)
    return out


def tokenize(segment):
    try:
        return shlex.split(segment)
    except ValueError:
        return [t.strip("'\"") for t in segment.split()]


def short_flags(token, valued=""):
    """Letters of a short-option cluster, stopping at an option that takes a value."""
    if not token.startswith("-") or token.startswith("--") or token == "-":
        return ""
    letters = ""
    for ch in token[1:]:
        letters += ch
        if ch in valued:
            break
    return letters


def long_matches(token, options, min_len=1):
    """True if token is --NAME[=v] and NAME is a prefix of an option (git accepts prefixes)."""
    if not token.startswith("--") or token == "--":
        return False
    name = token[2:].split("=", 1)[0]
    return len(name) >= min_len and any(opt.startswith(name) for opt in options)


def truthy(value):
    return value is None or value.strip().lower() not in FALSY


def parse_git(tokens, i):
    """Return (config_pairs, subcommand, args) for a git binary at tokens[i]."""
    config, i = [], i + 1
    while i < len(tokens):
        t = tokens[i]
        if t in GIT_VALUED:
            if t == "-c" and i + 1 < len(tokens):
                config.append(tokens[i + 1])
            i += 2
            continue
        if t.startswith("-"):
            i += 1
            continue
        return config, t, tokens[i + 1:]
    return config, None, []


def split_kv(pair):
    key, sep, value = pair.partition("=")
    return key.strip().lower(), (value if sep else None)


def is_rebase_key(key):
    return key == "pull.rebase" or (key.startswith("branch.") and key.endswith(".rebase"))


def check_alias(value, depth, config=(), args=()):
    """Expand a git alias as git does: `git <config> <value> <args>`, or `<value> <args>` for `!`."""
    tail = " ".join(shlex.quote(a) for a in args)
    if value.startswith("!"):
        return check_text(value[1:] + " " + tail, depth + 1)
    prefix = " ".join("-c " + shlex.quote(pair) for pair in config)
    return check_text(" ".join(("git", prefix, value, tail)), depth + 1)


def check_git(config, sub, args, depth):
    """Raise Denied for a forbidden git invocation, else return its verdict."""
    for pair in config:
        key, value = split_kv(pair)
        if key.startswith("alias.") and key[6:] == sub and value:
            rest = [c for c in config if c is not pair]
            return check_alias(value, depth, rest, args)
    for pair in config:
        key, value = split_kv(pair)
        if sub == "pull" and is_rebase_key(key) and truthy(value):
            raise Denied(REWRITE_MSG)
    if sub == "push":
        for a in args:
            if "f" in short_flags(a, valued="o") or long_matches(a, FORCE_LONG):
                raise Denied(FORCE_MSG)
            if a.startswith("+") and len(a) > 1:
                raise Denied(FORCE_MSG)
            if long_matches(a, TAG_LONG, min_len=2):
                raise Denied(PUBLISH_MSG)
        return ASK_PUSH
    if sub == "reset":
        if any(long_matches(a, ("hard",), min_len=2) for a in args):
            raise Denied(REWRITE_MSG)
    elif sub == "rebase":
        raise Denied(REWRITE_MSG)
    elif sub == "pull":
        for a in args:
            if "r" in short_flags(a, valued="sXj"):
                raise Denied(REWRITE_MSG)
            if long_matches(a, ("rebase",), min_len=3):
                value = a.partition("=")[2] if "=" in a else None
                if truthy(value):
                    raise Denied(REWRITE_MSG)
    elif sub == "tag":
        raise Denied(PUBLISH_MSG)
    elif sub == "config":
        words, skip = [], False
        for a in args:
            if skip:
                skip = False
            elif a in CONFIG_VALUED:
                skip = True
            elif not a.startswith("-"):
                words.append(a)
        if words[:1] == ["set"]:
            words = words[1:]
        if words:
            key = words[0].lower()
            value = words[1] if len(words) > 1 else None
            if is_rebase_key(key) and value is not None and truthy(value):
                raise Denied(REWRITE_MSG)
            if key.startswith("alias.") and value:
                check_alias(value, depth)
    return ALLOW


def check_tokens(tokens, depth):
    """Raise Denied, or return a verdict, for one simple command."""
    verdict = ALLOW
    names = [basename(t) for t in tokens]
    for i, name in enumerate(names):
        if name == "git":
            verdict = max(verdict, check_git(*parse_git(tokens, i), depth))
        elif name == "twine" and "upload" in tokens[i + 1:]:
            raise Denied(PUBLISH_MSG)
        elif name in PUBLISHERS and "publish" in tokens[i + 1:]:
            raise Denied(PUBLISH_MSG)
        elif name == "gh" and "release" in tokens[i + 1:]:
            raise Denied(PUBLISH_MSG)
        elif name == "rm":
            rest = tokens[i + 1:]
            recursive = any(
                "r" in short_flags(a).lower() or long_matches(a, ("recursive",), 3)
                for a in rest
            )
            if recursive and any(a in RM_TARGETS for a in rest):
                raise Denied(RM_MSG)
        elif name in FETCHERS:
            verdict = max(verdict, ASK_NETWORK)
    for t in tokens:
        if depth < 4 and re.search(r"[\s;|&`]|\$\(", t):
            verdict = max(verdict, check_text(t, depth + 1))
    return verdict


def reads_stdin_as_shell(tokens):
    names = [basename(t) for t in tokens]
    if set(names) & SHELLS:
        return True
    for i, name in enumerate(names):
        if name in ("sudo", "doas"):
            for a in tokens[i + 1:]:
                if set(short_flags(a, valued="ugpCDhrtTU")) & {"s", "i"}:
                    return True
                if long_matches(a, ("shell", "login"), min_len=2):
                    return True
    return False


def check_text(text, depth=0):
    """Raise Denied, or return a verdict, for a full command line."""
    if SHELL_SUBST_FETCH.search(text):
        raise Denied(PIPE_MSG)
    verdict = ALLOW
    fetched = False
    prev_op = None
    for segment, op in split_commands(text):
        tokens = tokenize(segment)
        # Any earlier download counts, not just the previous stage, so a fetch
        # inside a group, subshell, or $(...) piped into a shell is caught.
        if fetched and prev_op == "|" and reads_stdin_as_shell(tokens):
            raise Denied(PIPE_MSG)
        if FETCH_WORD.search(segment):
            fetched = True
        verdict = max(verdict, check_tokens(tokens, depth))
        prev_op = op
    return verdict


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        emit("deny", "Shell guard could not parse its input.")
        return 2
    command = data.get("command") if isinstance(data, dict) else None
    if not isinstance(command, str) or not command.strip():
        emit("deny", "Shell guard blocked a missing command.")
        return 0
    try:
        verdict = check_text(command)
    except Denied as exc:
        emit("deny", str(exc))
        return 0
    if verdict == ASK_PUSH:
        emit("ask", "Agent wants to push a branch. Allow?")
    elif verdict == ASK_NETWORK:
        emit("ask", "Agent wants network access: " + command)
    else:
        emit("allow")
    return 0


try:
    sys.exit(main())
except SystemExit:
    raise
except BaseException:
    emit("deny", "Shell guard crashed; blocking by default.")
    sys.exit(2)
PY

exec python3 -c "$GUARD_PY"
