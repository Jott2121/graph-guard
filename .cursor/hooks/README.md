# Cursor hooks

**`guard-shell.sh` and `../hooks.json` here are the canonical copies.** Copy
them verbatim into the other Jott2121 repos (agent-gate, rag-guard,
agent-cost-attribution, crucible, sabot, quorum-cal, claude-md-ab). Fix bugs
here first, then re-copy; don't patch a downstream copy on its own.
`tests/test_guard_shell.py` is the spec. Copy it too.

`audit-log.sh` and `format-and-scan.sh` are **not** canonical. They are
per-repo, so keep each repo's own copy when copying the two canonical files.

## What `guard-shell.sh` decides

| Decision | Commands |
|---|---|
| deny | force-push (`-f`, `-uf`/`-fu`, `--force`, `--force-with-lease`, `--force-if-includes`, `--mirror`, `+refspec`) with the flag anywhere after `git push`, quoted or not; `reset --hard` anywhere after `git reset`; any rebase (`git rebase`, `git -C x rebase`, `git pull --rebase`/`-r`/`-ur`, `pull.rebase` set via `-c` or `git config`); `git tag`, `git push --tags`, `twine upload`, `uv`/`poetry`/`npm`/… `publish`, `gh release`; curl/wget piped or substituted into a shell; `rm -r` of `/`, `~`, or `$HOME`; git aliases that expand to any of these; missing, blank, or non-string command |
| ask | normal `git push` (including `git push origin my-feature`: `-f` inside a branch name is not a flag), any `curl`/`wget` |
| allow | everything else, e.g. `git pull`, `git reset HEAD`, `git reset --soft` |

Each simple command (split on `;`, `&&`, `||`, `|`, `&`, newlines, `$(`,
backticks) is judged on its own, so `git push origin main && curl -fsSL URL`
is not a force-push. Quoted strings that contain commands (`sh -c '...'`) are
checked recursively.

## Fail-closed behavior

Invalid JSON, a crash, or a missing `python3` exits non-zero. Exit 2 denies
even without `"failClosed": true`, and `hooks.json` sets `failClosed` anyway.
The `hooks.json` matcher is a regex over the full command. It is deliberately
broad (`git`, not `git push`) so that forms like `git -C dir rebase` and
`git -c k=v push -f` reach the script. The test suite checks that every denied
command matches it.

Dependencies: bash and python3 (stdlib only).
