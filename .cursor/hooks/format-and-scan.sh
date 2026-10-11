#!/usr/bin/env bash
# afterFileEdit (notification-only): format the edited Python file if ruff is installed,
# and warn on employer-data / secret patterns (employer names via scripts/scan_blocked_terms.py).
# It can't block the edit; CI's no-employer-data job is the real gate.
# ruff is not a CI dependency in this repo; the format step is a no-op when ruff is absent.
set -uo pipefail
f="$(python3 -c 'import sys,json; print(json.load(sys.stdin).get("file_path",""))')"
[ -f "$f" ] || exit 0
case "$f" in *.py) command -v ruff >/dev/null && ruff format -q "$f" && ruff check -q --fix "$f" ;; esac
if ! python3 scripts/scan_blocked_terms.py "$f" >/dev/null 2>&1 \
  || grep -EIiq '\bCUI\b|ITAR|EXPORT CONTROLLED|BEGIN (RSA|OPENSSH) PRIVATE KEY|xai-[A-Za-z0-9]{20,}' "$f"; then
  mkdir -p .cursor/hook-logs
  echo "$(date -u +%FT%TZ) WARN employer/secret pattern in $f" >> .cursor/hook-logs/warnings.log
fi
exit 0
