"""Erzeugt aus wissen/ die maschinenlesbaren Dateien für den Chatbot.

- index/manifest.json : ein Eintrag je Dokument (Metadaten + Pfad)
- index/chunks.jsonl  : ein Textabschnitt je Zeile, mit Quellenangabe

Beide Dateien werden bei jedem Lauf vollständig neu erzeugt; massgeblich ist
allein der Inhalt von wissen/. Schema: docs/schnittstelle.md
"""

from __future__ import annotations

import json
from pathlib import Path

from . import dokument
from .chunks import zerlege

SCHEMA_VERSION = 1
_FELDER = (
    "titel", "quelle", "sharepoint_quelle", "sharepoint_pfad", "sharepoint_id",
    "dateityp", "geaendert_am", "geaendert_von", "abgeglichen_am",
)


def baue_index(basis: Path, ziel: Path, max_zeichen: int = 1500) -> tuple[int, int]:
    ziel.mkdir(parents=True, exist_ok=True)
    dokumente = []
    anzahl_chunks = 0
    with (ziel / "chunks.jsonl").open("w", encoding="utf-8") as out:
        for pfad, meta, text in dokument.alle(basis):
            rel = pfad.relative_to(basis.parent).as_posix()
            eintrag = {k: meta.get(k) for k in _FELDER}
            eintrag["datei"] = rel
            teile = zerlege(text, max_zeichen)
            eintrag["zeichen"] = len(text)
            eintrag["chunks"] = len(teile)
            dokumente.append(eintrag)
            for nr, teil in enumerate(teile):
                out.write(json.dumps({
                    "id": f"{meta['sharepoint_id']}#{nr}",
                    "dokument_id": meta["sharepoint_id"],
                    "titel": meta.get("titel"),
                    "quelle": meta.get("quelle"),
                    "datei": rel,
                    "geaendert_am": meta.get("geaendert_am"),
                    "ueberschrift": teil["ueberschrift"],
                    "text": teil["text"],
                }, ensure_ascii=False) + "\n")
                anzahl_chunks += 1
    manifest = {"schema_version": SCHEMA_VERSION, "dokumente": dokumente}
    (ziel / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    return len(dokumente), anzahl_chunks
