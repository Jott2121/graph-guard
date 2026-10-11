#!/usr/bin/env bash
# beforeShellExecution guard. Reads {"command": "...", "cwd": "..."} on stdin.
# Denies irreversible / publishing commands; asks on network fetches. Fails closed (hooks.json failClosed: true).
# The matcher includes `git pull`, so `git pull --rebase` reaches the rebase deny arm.
# A plain `git pull` does not match that arm and is allowed.
set -euo pipefail
input="$(cat)"
# json.load must be free to fail: invalid JSON exits non-zero and failClosed denies.
# A well-formed payload with a missing, blank, or non-string command is an explicit deny.
cmd="$(printf '%s' "$input" | python3 -c 'import json,sys
data=json.load(sys.stdin)
cmd=data.get("command") if isinstance(data, dict) else None
sys.stdout.write(cmd if isinstance(cmd, str) else "")')"
# json.dumps, not printf: a curl/wget command can contain quotes or backslashes,
# and an unescaped user_message is invalid JSON (the ask decision never lands).
deny() { python3 -c 'import json,sys; msg=sys.argv[1]; print(json.dumps({"permission":"deny","user_message":msg,"agent_message":msg+" Open a PR instead; a human will do this step."}))' "$1"; exit 0; }
ask()  { python3 -c 'import json,sys; print(json.dumps({"permission":"ask","user_message":sys.argv[1]}))' "$1"; exit 0; }
if [ -z "${cmd//[[:space:]]/}" ]; then
  deny "Missing or empty command blocked by repo policy."
fi
# Flags may follow other arguments, and short options may be clustered.
# Shell separators (; | &) are token boundaries, so `git pull -r; true` and
# `git push origin -uf | cat` deny the same way as the unchained forms.
# A plain `git pull` and `git push -u` (no f) stay allowed / ask.
segments="${cmd//[;|&]/$'\n'}"
while IFS= read -r segment || [ -n "$segment" ]; do
  [ -z "${segment//[[:space:]]/}" ] && continue
  _push=0
  _pull=0
  _reset=0
  _force=0
  _rebase=0
  _hard=0
  _in_git=0
  _skip_next=0
  _tokens=()
  IFS=$' \t' read -ra _tokens <<< "$segment"
  for token in "${_tokens[@]}"; do
    token="${token#\"}"
    token="${token%\"}"
    token="${token#\'}"
    token="${token%\'}"
    if [ "$_skip_next" -eq 1 ]; then
      _skip_next=0
      continue
    fi
    case "$token" in
      git) _in_git=1 ;;
      -C|-c) [ "$_in_git" -eq 1 ] && _skip_next=1 ;;
      push)  [ "$_in_git" -eq 1 ] && _push=1;  _in_git=0 ;;
      pull)  [ "$_in_git" -eq 1 ] && _pull=1;  _in_git=0 ;;
      reset) [ "$_in_git" -eq 1 ] && _reset=1; _in_git=0 ;;
      --force|--force=*|--force-with-lease|--force-with-lease=*) _force=1 ;;
      --rebase|--rebase=*) _rebase=1 ;;
      --hard|--hard=*) _hard=1 ;;
      --*) ;;
      -*)
        [[ "$token" == *f* ]] && _force=1
        [[ "$token" == *r* ]] && _rebase=1
        ;;
    esac
  done
  if [ "$_push" -eq 1 ] && [ "$_force" -eq 1 ]; then
    deny "Force-push blocked by repo policy."
  fi
  if [ "$_pull" -eq 1 ] && [ "$_rebase" -eq 1 ]; then
    deny "History rewrite blocked by repo policy."
  fi
  if [ "$_reset" -eq 1 ] && [ "$_hard" -eq 1 ]; then
    deny "History rewrite blocked by repo policy."
  fi
done <<< "$segments"
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
