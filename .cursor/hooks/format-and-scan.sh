#!/usr/bin/env bash
# afterFileEdit (notification-only): format the edited Python file if ruff is installed,
# and warn on employer-name / export-control / secret patterns.
# It can't block the edit; CI's no-employer-data job is the real gate.
# ruff is not a CI dependency in this repo; the format step is a no-op when ruff is absent.
set -uo pipefail
f="$(python3 -c 'import sys,json; print(json.load(sys.stdin).get("file_path",""))')"
[ -f "$f" ] || exit 0
case "$f" in *.py) command -v ruff >/dev/null && ruff format -q "$f" && ruff check -q --fix "$f" ;; esac
warn() {
  mkdir -p .cursor/hook-logs
  echo "$(date -u +%FT%TZ) WARN $1 in $f" >> .cursor/hook-logs/warnings.log
}
# Any non-zero exit (hit or scanner failure) warns, so a broken scanner is not silent.
python3 scripts/scan_blocked_terms.py "$f" >/dev/null 2>&1 || warn "employer-name pattern (or scanner failure)"
if grep -EIiq '\bCUI\b|ITAR|EXPORT CONTROLLED|BEGIN (RSA|OPENSSH) PRIVATE KEY|xai-[A-Za-z0-9]{20,}' "$f"; then
  warn "export-control/secret pattern"
fi
exit 0
