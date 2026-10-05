# Schnittstelle für den Chatbot (Schema-Version 1)

Das Chatbot-Repository liest ausschliesslich die Dateien unter `index/`. Sie
werden bei jedem Abgleich vollständig neu erzeugt. Änderungen am Format
erhöhen `schema_version`.

## `index/chunks.jsonl`

Eine JSON-Zeile je Textabschnitt (Abschnitte folgen den Überschriften des
Dokuments, Zielgrösse `chunks.max_zeichen` in `config/sharepoint.yaml`):

```json
{
  "id": "01ABC…#3",
  "dokument_id": "01ABC…",
  "titel": "Reiserichtlinie",
  "quelle": "https://contoso.sharepoint.com/sites/Wissen/Shared%20Documents/Reiserichtlinie.docx",
  "datei": "wissen/beispiel/Richtlinien/Reiserichtlinie.docx.md",
  "geaendert_am": "2026-09-30T08:12:00Z",
  "ueberschrift": "Reiserichtlinie > Spesen",
  "text": "## Spesen\n\nMax. 50 € pro Tag."
}
```

- `id` ist stabil, solange sich das Dokument nicht ändert – geeignet als
  Schlüssel für einen Embedding-Cache.
- `quelle` ist der SharePoint-Link und soll in jeder Antwort als
  Quellenangabe erscheinen.

## `index/manifest.json`

```json
{
  "schema_version": 1,
  "dokumente": [
    {
      "titel": "Reiserichtlinie",
      "quelle": "https://…",
      "sharepoint_quelle": "beispiel",
      "sharepoint_pfad": "/Richtlinien/Reiserichtlinie.docx",
      "sharepoint_id": "01ABC…",
      "dateityp": "docx",
      "geaendert_am": "2026-09-30T08:12:00Z",
      "geaendert_von": "Erika Muster",
      "abgeglichen_am": "2026-10-05T06:17:42+00:00",
      "datei": "wissen/beispiel/Richtlinien/Reiserichtlinie.docx.md",
      "zeichen": 5120,
      "chunks": 4
    }
  ]
}
```

## Empfohlener Aufbau des Chatbot-Repositorys

1. **Daten beziehen:** dieses Repo als Git-Submodul einbinden oder
   `index/chunks.jsonl` per GitHub-API/Raw-URL laden (bei privatem Repo mit
   Token). Ein Workflow im Chatbot-Repo kann per `repository_dispatch` nach
   jedem Abgleich ausgelöst werden.
2. **Suche (Retrieval):** zu Beginn genügt eine Volltextsuche (BM25) über die
   Abschnitte; bei Bedarf später Embeddings ergänzen. Rückgabe der besten
   5–10 Abschnitte.
3. **Antwort:** die gefundenen Abschnitte mit Titel und `quelle` in den Prompt
   eines Claude-Modells geben, mit der Anweisung, nur auf dieser Grundlage zu
   antworten, Quellen zu nennen und bei fehlender Grundlage „nicht in der
   Wissensbasis“ zu sagen.
4. **Oberfläche:** z. B. einfache Web-App, Microsoft-Teams-Bot oder Slack.

Weiterführend: Anthropic, *Contextual Retrieval*:
<https://www.anthropic.com/news/contextual-retrieval>; Anthropic,
*Citations*: <https://docs.claude.com/en/docs/build-with-claude/citations>
