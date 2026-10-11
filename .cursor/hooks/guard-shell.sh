#!/usr/bin/env bash
# beforeShellExecution guard. Reads {"command": "...", "cwd": "..."} on stdin.
# Denies irreversible / publishing commands; asks on network fetches. Fails closed (hooks.json failClosed: true).
# "rebase" matches `git rebase` and `git pull --rebase`.
set -euo pipefail
input="$(cat)"
cmd="$(printf '%s' "$input" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("command",""))')"
# json.dumps, not printf: a curl/wget command can contain quotes or backslashes,
# and an unescaped user_message is invalid JSON (the ask decision never lands).
deny() { python3 -c 'import json,sys; msg=sys.argv[1]; print(json.dumps({"permission":"deny","user_message":msg,"agent_message":msg+" Open a PR instead; a human will do this step."}))' "$1"; exit 0; }
ask()  { python3 -c 'import json,sys; print(json.dumps({"permission":"ask","user_message":sys.argv[1]}))' "$1"; exit 0; }
case "$cmd" in
  *"push --force"*|*"push -f"*|*"--force-with-lease"*) deny "Force-push blocked by repo policy." ;;
  *"reset --hard"*|*"rebase"*)                        deny "History rewrite blocked by repo policy." ;;
  *"git tag"*|*"twine upload"*|*"uv publish"*|*"gh release"*) deny "Releases/publishing are human-only." ;;
  *"rm -rf /"*|*"rm -rf ~"*|*'rm -rf $HOME'*)         deny "Destructive delete blocked." ;;
  *"curl"*"| sh"*|*"curl"*"| bash"*|*"wget"*"| sh"*)   deny "Pipe-to-shell blocked." ;;
  *"git push"*)                                       ask  "Agent wants to push a branch. Allow?" ;;
  *"curl"*|*"wget"*)                                  ask  "Agent wants network access: $cmd" ;;
esac
printf '{"permission":"allow"}\n'
