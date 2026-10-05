"""Lesen und Schreiben der Markdown-Dokumente mit YAML-Frontmatter."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_UNERLAUBT = re.compile(r'[<>:"\\|?*\x00-\x1f]')


def sauberer_name(name: str) -> str:
    """Macht einen SharePoint-Namen dateisystemtauglich, lässt ihn aber lesbar (Umlaute bleiben)."""
    name = _UNERLAUBT.sub("_", name).strip().strip(".")
    return name or "_"


def ziel_pfad(basis: Path, quelle: str, sp_pfad: str) -> Path:
    """'/Ordner/Datei.docx' -> basis/quelle/Ordner/Datei.docx.md

    Die Originalendung bleibt erhalten, damit 'Handbuch.docx' und
    'Handbuch.pdf' nicht kollidieren.
    """
    teile = [sauberer_name(t) for t in sp_pfad.strip("/").split("/") if t]
    return basis.joinpath(sauberer_name(quelle), *teile[:-1], teile[-1] + ".md")


def schreibe(pfad: Path, meta: dict, text: str) -> None:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    kopf = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
    pfad.write_text(f"---\n{kopf}\n---\n\n{text.strip()}\n", encoding="utf-8")


def lese(pfad: Path) -> tuple[dict, str]:
    inhalt = pfad.read_text(encoding="utf-8")
    if not inhalt.startswith("---\n"):
        return {}, inhalt
    ende = inhalt.find("\n---\n", 4)
    if ende == -1:
        return {}, inhalt
    meta = yaml.safe_load(inhalt[4:ende]) or {}
    return meta, inhalt[ende + 5 :].lstrip("\n")


def alle(basis: Path):
    """Alle Dokumente unter basis als (pfad, meta, text)."""
    for pfad in sorted(basis.rglob("*.md")):
        meta, text = lese(pfad)
        if meta.get("sharepoint_id"):
            yield pfad, meta, text
