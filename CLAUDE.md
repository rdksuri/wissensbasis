# Hinweise für Claude

Dieses Repository ist die zentrale Wissensbasis der Nutzerin bzw. des Nutzers
und Grundlage weiterer Projekte (u. a. eines Chatbots in einem zweiten Repo).

## Sprache und Stil
- Antworten, Commit-Nachrichten und Dokumentation auf **Hochdeutsch**.
- Aussagen über Inhalte der Wissensbasis immer mit **Quellenangabe**: Titel
  und SharePoint-Link (`quelle` im YAML-Kopf) bzw. Pfad unter `wissen/`.

## Regeln
- `wissen/`, `index/` und `state/` werden vom Abgleich erzeugt. **Nicht von
  Hand bearbeiten** – Änderungen gehören in SharePoint; sie werden beim
  nächsten Lauf überschrieben.
- Nach Änderungen am Code: `python -m pytest -q`.
- Das Format von `index/` ist eine Schnittstelle (`docs/schnittstelle.md`).
  Inkompatible Änderungen nur mit Erhöhung von `schema_version` und Hinweis
  an das Chatbot-Repo.
- Keine Zugangsdaten ins Repo; sie liegen als GitHub-Variablen/-Secrets vor.

## Fragen zur Wissensbasis beantworten
1. In `index/manifest.json` passende Dokumente suchen, dann per Grep in
   `wissen/` nach Begriffen suchen.
2. Die relevanten Markdown-Dateien lesen.
3. Antwort mit Quellen (Titel + Link, Stand `geaendert_am`) geben; bei fehlender
   Grundlage dies offen sagen.

## Befehle
- `python -m wissensbasis sync [--voll]` – SharePoint abgleichen (braucht
  `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, ggf. `AZURE_CLIENT_SECRET`)
- `python -m wissensbasis index` – Index aus `wissen/` neu erzeugen
