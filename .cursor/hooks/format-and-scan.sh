#!/usr/bin/env bash
# afterFileEdit (notification-only): format the edited Python file if ruff is installed,
# and warn on employer-data / secret patterns.
# It can't block the edit; CI's no-employer-data job is the real gate.
# ruff is not a CI dependency in this repo; the format step is a no-op when ruff is absent.
# Employer names are never written in the repo. They come from EMPLOYER_MARKERS
# (a case-insensitive extended regex; newlines separate alternatives). When it is
# unset or blank, only the generic export-control and secret patterns run.
set -uo pipefail
f="$(python3 -c 'import sys,json; print(json.load(sys.stdin).get("file_path",""))')"
[ -f "$f" ] || exit 0
case "$f" in *.py) command -v ruff >/dev/null && ruff format -q "$f" && ruff check -q --fix "$f" ;; esac
pattern='\bCUI\b|ITAR|EXPORT CONTROLLED|BEGIN (RSA|OPENSSH) PRIVATE KEY|xai-[A-Za-z0-9]{20,}'
markers=""
while IFS= read -r line || [ -n "$line" ]; do
  line="$(printf '%s' "$line" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
  if [ -n "$line" ]; then markers="${markers:+$markers|}$line"; fi
done <<< "${EMPLOYER_MARKERS:-}"
# A pattern that matches an empty line (`a||b`, a lone `|`) matches everything.
if [ -n "$markers" ] && printf '\n' | grep -Eq -- "$markers"; then
  mkdir -p .cursor/hook-logs
  echo "$(date -u +%FT%TZ) WARN EMPLOYER_MARKERS matches an empty line; ignoring it" >> .cursor/hook-logs/warnings.log
  markers=""
fi
[ -n "$markers" ] && pattern="$markers|$pattern"
if grep -EIiq -- "$pattern" "$f"; then
  mkdir -p .cursor/hook-logs
  echo "$(date -u +%FT%TZ) WARN employer/secret pattern in $f" >> .cursor/hook-logs/warnings.log
fi
exit 0
