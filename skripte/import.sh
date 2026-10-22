#!/bin/bash
# Importiert die per OneDrive synchronisierten Ordner in die Wissensbasis (macOS/Linux).
#   skripte/import.sh          nur lokal
#   skripte/import.sh --push   zusätzlich committen und zu GitHub pushen
#                              ACHTUNG: öffentliches Repo = Inhalte für alle lesbar
set -euo pipefail
cd "$(dirname "$0")/.."
exec >>import.log 2>&1
echo "=== $(date '+%Y-%m-%d %H:%M:%S') ==="

PUSH=false
[[ "${1:-}" == "--push" ]] && PUSH=true

PYTHON=python3
[[ -x .venv/bin/python ]] && PYTHON=.venv/bin/python

$PUSH && git pull --ff-only
"$PYTHON" -m wissensbasis import-ordner

if $PUSH; then
  git add -A wissen index
  if git diff --cached --quiet; then
    echo "Keine Änderungen."
  else
    git commit -m "Ordner-Import $(date '+%Y-%m-%d %H:%M')"
    git push
  fi
fi
