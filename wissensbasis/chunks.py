"""Zerlegt Markdown in überschriftenbezogene Abschnitte für die Suche im Chatbot."""

from __future__ import annotations

import re

_UEBERSCHRIFT = re.compile(r"^(#{1,6})\s+(.*)$")


def _abschnitte(text: str):
    """Liefert (Überschriftenpfad, Text) je Abschnitt."""
    pfad: list[str] = []
    puffer: list[str] = []
    for zeile in text.splitlines():
        m = _UEBERSCHRIFT.match(zeile)
        if m:
            if "".join(puffer).strip():
                yield " > ".join(pfad), "\n".join(puffer).strip()
            puffer = [zeile]
            ebene = len(m.group(1))
            pfad = pfad[: ebene - 1] + [""] * max(0, ebene - 1 - len(pfad)) + [m.group(2).strip()]
            pfad = [p for p in pfad if p]
        else:
            puffer.append(zeile)
    if "".join(puffer).strip():
        yield " > ".join(pfad), "\n".join(puffer).strip()


def _teile(text: str, max_zeichen: int):
    """Zerlegt zu lange Abschnitte an Absatzgrenzen (notfalls hart)."""
    if len(text) <= max_zeichen:
        yield text
        return
    aktuell = ""
    for absatz in re.split(r"\n\s*\n", text):
        while len(absatz) > max_zeichen:
            if aktuell:
                yield aktuell
                aktuell = ""
            yield absatz[:max_zeichen]
            absatz = absatz[max_zeichen:]
        if aktuell and len(aktuell) + len(absatz) + 2 > max_zeichen:
            yield aktuell
            aktuell = absatz
        else:
            aktuell = f"{aktuell}\n\n{absatz}" if aktuell else absatz
    if aktuell.strip():
        yield aktuell


def zerlege(text: str, max_zeichen: int = 1500) -> list[dict]:
    ergebnis = []
    for ueberschrift, abschnitt in _abschnitte(text):
        for teil in _teile(abschnitt, max_zeichen):
            ergebnis.append({"ueberschrift": ueberschrift, "text": teil.strip()})
    return ergebnis
