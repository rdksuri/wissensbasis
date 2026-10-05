"""Umwandlung von Office-/PDF-Dateien in Markdown mit Microsofts MarkItDown.

Quelle: https://github.com/microsoft/markitdown
"""

from __future__ import annotations

import tempfile
from pathlib import Path

_TEXT = {".md", ".txt", ".csv"}


def nach_markdown(dateiname: str, inhalt: bytes) -> str:
    endung = Path(dateiname).suffix.lower()
    if endung in _TEXT:
        return inhalt.decode("utf-8", errors="replace")

    from markitdown import MarkItDown  # erst hier importieren: schwere Abhängigkeit

    with tempfile.TemporaryDirectory() as tmp:
        datei = Path(tmp) / f"datei{endung}"
        datei.write_bytes(inhalt)
        return MarkItDown().convert(str(datei)).text_content
