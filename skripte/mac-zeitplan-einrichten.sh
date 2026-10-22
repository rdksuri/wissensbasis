#!/bin/bash
# Richtet den stündlichen Import per launchd ein (läuft, solange du angemeldet bist).
#   skripte/mac-zeitplan-einrichten.sh            nur lokal
#   skripte/mac-zeitplan-einrichten.sh --push     mit Hochladen zu GitHub
#   skripte/mac-zeitplan-einrichten.sh --entfernen
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="ch.wissensbasis.import"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
if [[ "${1:-}" == "--entfernen" ]]; then
  rm -f "$PLIST"; echo "Zeitplan entfernt."; exit 0
fi

ARG=""
[[ "${1:-}" == "--push" ]] && ARG="<string>--push</string>"

mkdir -p "$(dirname "$PLIST")"
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>$REPO/skripte/import.sh</string>$ARG</array>
  <key>StartInterval</key><integer>3600</integer>
  <key>RunAtLoad</key><true/>
</dict>
</plist>
PLIST
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Eingerichtet: stündlicher Import, Protokoll in $REPO/import.log"
