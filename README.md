# Wissensbasis

Zentrale, versionierte Wissensbasis aus SharePoint-Dokumenten. Ein geplanter
GitHub-Actions-Workflow liest die konfigurierten SharePoint-Bibliotheken über
die Microsoft Graph API, wandelt Word-, PowerPoint-, Excel- und PDF-Dateien in
Markdown um und legt sie hier ab. Daraus entsteht ein Index, den ein separater
Chatbot (zweites Repository) zur Beantwortung von Fragen nutzt.

```
SharePoint ──(Graph-API, Delta)──▶ wissen/**.md ──▶ index/manifest.json
                                                  └▶ index/chunks.jsonl ──▶ Chatbot-Repo
```

## Aufbau

| Pfad | Inhalt |
|---|---|
| `config/sharepoint.yaml` | Welche Sites/Bibliotheken/Ordner und Dateitypen abgeglichen werden |
| `wissen/<quelle>/…/<Datei>.<endung>.md` | Ein Markdown-Dokument je SharePoint-Datei, mit Metadaten im YAML-Kopf (u. a. Link zur Quelle) – **automatisch erzeugt** |
| `index/manifest.json` | Verzeichnis aller Dokumente |
| `index/chunks.jsonl` | Textabschnitte mit Quellenangabe für die Suche im Chatbot |
| `state/` | Delta-Token und Ordnerstruktur je Quelle (nicht von Hand ändern) |
| `wissensbasis/` | Python-Code für Abgleich und Index |
| `docs/einrichtung.md` | Einmalige Einrichtung (Entra-App, Berechtigungen, GitHub-Variablen) |
| `docs/schnittstelle.md` | Datenformat für das Chatbot-Repository |

## Betrieb

- **Automatisch:** werktags 06:17 und 13:17 UTC (`.github/workflows/sharepoint-sync.yml`).
- **Manuell:** GitHub → *Actions* → *SharePoint-Abgleich* → *Run workflow*
  (optional „Vollabgleich“).
- **Lokal:**
  ```bash
  pip install -r requirements-dev.txt
  export AZURE_TENANT_ID=… AZURE_CLIENT_ID=… AZURE_CLIENT_SECRET=…
  python -m wissensbasis sync      # abgleichen + Index bauen
  python -m wissensbasis index     # nur Index neu bauen
  python -m pytest -q              # Tests (ohne SharePoint-Zugang)
  ```

Jeder Lauf erzeugt nur dann einen Commit, wenn sich etwas geändert hat. Die
Git-Historie ist damit zugleich das Änderungsprotokoll der Wissensbasis.

## Erste Schritte

1. Einrichtung gemäss [`docs/einrichtung.md`](docs/einrichtung.md).
2. `config/sharepoint.yaml` mit eigener Site und Bibliothek füllen.
3. Workflow einmal manuell starten und die Zusammenfassung im Actions-Lauf prüfen.

## Quellen

- Microsoft Graph, *driveItem: delta*: <https://learn.microsoft.com/graph/api/driveitem-delta>
- Microsoft Graph, *Selected-Berechtigungen*: <https://learn.microsoft.com/graph/permissions-selected-overview>
- Microsoft Entra, *Workload Identity Federation*: <https://learn.microsoft.com/entra/workload-id/workload-identity-federation>
- Microsoft MarkItDown (Konvertierung nach Markdown): <https://github.com/microsoft/markitdown>
- GitHub Actions, *schedule*-Ereignis: <https://docs.github.com/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows#schedule>
