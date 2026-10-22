#!/bin/bash
# Einrichtung der Wissensbasis auf dem Mac – ein Befehl, keine Admin-Rechte nötig.
#
#   curl -fsSL https://raw.githubusercontent.com/rdksuri/wissensbasis/main/skripte/mac-einrichten.sh | bash
#
# Was passiert:
#  1. uv installieren (Python-Paketmanager von Astral, lädt Python selbst; ~/.local/bin)
#  2. Wissensbasis nach ~/wissensbasis holen (git, sonst ZIP-Download)
#  3. Python 3.12 + Abhängigkeiten in ~/wissensbasis/.venv installieren
#  4. OneDrive-Ordner suchen und in config/lokal.yaml eintragen
#  5. Ersten Import ausführen
#
# Umgebungsvariablen (optional):
#   WB_ZIEL    Zielordner        (Standard: ~/wissensbasis)
#   WB_BRANCH  Git-Branch        (Standard: main)
#   WB_ORDNER  OneDrive-Ordner   (Standard: "INT-Rettungsdienst - Dokumente")
#   WB_QUELLE  Quellenname       (Standard: rettungsdienst)
set -euo pipefail

ZIEL="${WB_ZIEL:-$HOME/wissensbasis}"
BRANCH="${WB_BRANCH:-main}"
ORDNER="${WB_ORDNER:-INT-Rettungsdienst - Dokumente}"
QUELLE="${WB_QUELLE:-rettungsdienst}"
REPO="https://github.com/rdksuri/wissensbasis"

schritt() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

schritt "1/5 uv (Python-Verwaltung) prüfen"
export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
uv --version

schritt "2/5 Wissensbasis nach $ZIEL holen"
if [[ -d "$ZIEL/.git" ]]; then
  git -C "$ZIEL" fetch origin "$BRANCH"
  if ! git -C "$ZIEL" merge --ff-only "origin/$BRANCH"; then
    # z. B. nach bereinigter Historie auf GitHub: Programmstand übernehmen.
    # Unberührt bleiben config/lokal.yaml, .venv und die Dokumente in OneDrive;
    # wissen/ und index/ werden im Schritt 5 neu erzeugt.
    echo "Lokale Kopie weicht ab – wird auf den aktuellen Stand gesetzt."
    git -C "$ZIEL" reset --hard "origin/$BRANCH"
  fi
elif [[ -f "$ZIEL/requirements.txt" ]]; then
  echo "Vorhanden (ohne git) – wird aktualisiert."
  tmp="$(mktemp -d)"
  curl -fsSL "$REPO/archive/refs/heads/$BRANCH.zip" -o "$tmp/wb.zip"
  unzip -q "$tmp/wb.zip" -d "$tmp"
  rsync -a --exclude wissen --exclude index --exclude state --exclude .venv \
        --exclude config/lokal.yaml "$tmp"/wissensbasis-*/ "$ZIEL"/
  rm -rf "$tmp"
elif git --version >/dev/null 2>&1; then
  git clone -b "$BRANCH" "$REPO.git" "$ZIEL"
else
  tmp="$(mktemp -d)"
  curl -fsSL "$REPO/archive/refs/heads/$BRANCH.zip" -o "$tmp/wb.zip"
  unzip -q "$tmp/wb.zip" -d "$tmp"
  mv "$tmp"/wissensbasis-* "$ZIEL"
  rm -rf "$tmp"
fi
cd "$ZIEL"

schritt "3/5 Python 3.12 und Abhängigkeiten installieren"
[[ -x .venv/bin/python ]] || uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -q -r requirements.txt
.venv/bin/python --version

schritt "4/5 OneDrive-Ordner „$ORDNER“ suchen"
if [[ -f config/lokal.yaml ]]; then
  echo "config/lokal.yaml existiert bereits – unverändert gelassen."
else
  shopt -s nullglob
  treffer=("$HOME"/Library/CloudStorage/OneDrive-*/"$ORDNER")
  set +u; anzahl=${#treffer[@]}; set -u   # bash 3.2 (macOS) verträgt leere Arrays mit -u schlecht
  if [[ $anzahl -ne 1 ]]; then
    echo "Ordner nicht eindeutig gefunden ($anzahl Treffer)."
    echo "Bitte in Teams „Verknüpfung zu OneDrive hinzufügen“ ausführen und das Skript erneut starten,"
    echo "oder config/lokal.beispiel.yaml nach config/lokal.yaml kopieren und den Pfad eintragen."
    exit 1
  fi
  # Pfad mit ~ speichern, damit kein Benutzername in Dateien steht
  pfad="~${treffer[0]#"$HOME"}"
  cat > config/lokal.yaml <<YAML
# Automatisch erzeugt von skripte/mac-einrichten.sh – nicht im Repo.
quellen:
  - name: $QUELLE
    lokaler_pfad: '$pfad'
YAML
  echo "Eingetragen: $pfad"
fi

schritt "5/5 Erster Import (kann bei vielen Dateien etwas dauern)"
echo "Falls macOS fragt, ob Terminal auf OneDrive zugreifen darf: „Erlauben“."
.venv/bin/python -m wissensbasis import-ordner

cat <<TEXT

Fertig. Die Wissensbasis liegt in $ZIEL (Ordner wissen/ und index/).

Stündlich automatisch aktualisieren (nur lokal, ohne Hochladen):
  $ZIEL/skripte/mac-zeitplan-einrichten.sh
TEXT
