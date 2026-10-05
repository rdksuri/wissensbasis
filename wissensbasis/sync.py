"""Inkrementeller Abgleich einer SharePoint-Bibliothek nach wissen/.

Ablauf je Quelle:
1. Delta-Abfrage (beim ersten Lauf bzw. nach Ablauf des deltaLinks: alles).
2. Ordnerstruktur im Zustand nachführen – Delta liefert keine Pfade, daher
   werden sie aus den Eltern-IDs rekonstruiert.
3. Geänderte Dateien herunterladen und als Markdown speichern; gelöschte
   oder aus dem Geltungsbereich verschobene Dateien entfernen.
4. Bereits vorhandene Dokumente an umbenannte/verschobene Ordner anpassen.

Quelle zum Delta-Verhalten (u. a. fehlender parentReference.path, nur Root
in SharePoint, HTTP 410 bei abgelaufenem Token):
https://learn.microsoft.com/graph/api/driveitem-delta
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import dokument
from .graph import DeltaAbgelaufen
from .konvertierung import nach_markdown

log = logging.getLogger(__name__)


@dataclass
class Bericht:
    neu: list[str] = field(default_factory=list)
    aktualisiert: list[str] = field(default_factory=list)
    verschoben: list[str] = field(default_factory=list)
    geloescht: list[str] = field(default_factory=list)
    uebersprungen: list[str] = field(default_factory=list)
    fehler: list[str] = field(default_factory=list)

    def hat_aenderungen(self) -> bool:
        return bool(self.neu or self.aktualisiert or self.verschoben or self.geloescht)

    def als_markdown(self) -> str:
        zeilen = ["## SharePoint-Abgleich", ""]
        for titel, liste in [
            ("Neu", self.neu),
            ("Aktualisiert", self.aktualisiert),
            ("Verschoben/umbenannt", self.verschoben),
            ("Gelöscht", self.geloescht),
            ("Übersprungen", self.uebersprungen),
            ("Fehler", self.fehler),
        ]:
            zeilen.append(f"**{titel}: {len(liste)}**")
            zeilen.extend(f"- {e}" for e in liste[:200])
            zeilen.append("")
        return "\n".join(zeilen)


def _jetzt() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Abgleich:
    def __init__(self, client, quelle: dict, config: dict, basis: Path, zustand_dir: Path):
        self.client = client
        self.quelle = quelle
        self.name = quelle["name"]
        self.basis = basis
        self.zustand_datei = zustand_dir / f"{dokument.sauberer_name(self.name)}.json"
        self.endungen = {e.lower() for e in config.get("dateitypen", [])}
        self.max_bytes = int(config.get("max_groesse_mb", 50)) * 1024 * 1024
        self.ordner_filter = [
            "/" + o.strip("/") for o in quelle.get("ordner") or [] if o.strip("/")
        ]

    # --- Zustand ---------------------------------------------------------

    def _lade_zustand(self) -> dict:
        if self.zustand_datei.exists():
            return json.loads(self.zustand_datei.read_text(encoding="utf-8"))
        return {}

    def _speichere_zustand(self, zustand: dict) -> None:
        self.zustand_datei.parent.mkdir(parents=True, exist_ok=True)
        self.zustand_datei.write_text(
            json.dumps(zustand, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    # --- Pfade -----------------------------------------------------------

    def _ordner_pfad(self, ordner: dict, ordner_id: str | None) -> str | None:
        """Pfad eines Ordners relativ zur Bibliothek ('' = Wurzel), None = unbekannt."""
        teile = []
        gesehen = set()
        while ordner_id and ordner_id not in gesehen:
            gesehen.add(ordner_id)
            eintrag = ordner.get(ordner_id)
            if eintrag is None:
                return None
            if eintrag.get("wurzel"):
                return "/".join(reversed(teile))
            teile.append(eintrag["name"])
            ordner_id = eintrag.get("eltern")
        return None

    def _im_bereich(self, sp_pfad: str) -> bool:
        if not self.ordner_filter:
            return True
        return any(sp_pfad == o or sp_pfad.startswith(o + "/") for o in self.ordner_filter)

    def _relevant(self, name: str, groesse: int) -> str | None:
        """Grund, warum eine Datei übersprungen wird, sonst None."""
        endung = Path(name).suffix.lower()
        if name.startswith("~$"):
            return "temporäre Office-Datei"
        if self.endungen and endung not in self.endungen:
            return f"Dateityp {endung or '(ohne)'} nicht konfiguriert"
        if groesse > self.max_bytes:
            return f"zu gross ({groesse // (1024 * 1024)} MB)"
        return None

    # --- Hauptablauf -----------------------------------------------------

    def ausfuehren(self, drive_id: str, bericht: Bericht, voll: bool = False) -> None:
        zustand = self._lade_zustand()
        if zustand.get("drive_id") != drive_id or voll:
            zustand = {}
        ordner: dict = zustand.get("ordner", {})
        delta_link = zustand.get("delta_link")

        try:
            eintraege, neuer_link = self.client.delta(drive_id, delta_link)
        except DeltaAbgelaufen:
            log.warning("%s: deltaLink abgelaufen, starte Vollabgleich", self.name)
            ordner, delta_link = {}, None
            eintraege, neuer_link = self.client.delta(drive_id, None)
        vollabgleich = delta_link is None

        # 1. Ordnerstruktur nachführen (vor den Dateien, Reihenfolge egal)
        for e in eintraege:
            if "root" in e:
                ordner[e["id"]] = {"name": "", "wurzel": True}
            elif "folder" in e:
                if "deleted" in e:
                    ordner.pop(e["id"], None)
                else:
                    ordner[e["id"]] = {
                        "name": e["name"],
                        "eltern": e.get("parentReference", {}).get("id"),
                    }

        # 2. Bekannte Dokumente dieser Quelle einlesen
        bekannt: dict[str, tuple[Path, dict, str]] = {}
        quell_dir = self.basis / dokument.sauberer_name(self.name)
        if quell_dir.exists():
            for pfad, meta, text in dokument.alle(quell_dir):
                bekannt[meta["sharepoint_id"]] = (pfad, meta, text)

        gesehen: set[str] = set()

        # 3. Dateien verarbeiten
        for e in eintraege:
            if "file" not in e and not ("deleted" in e and e["id"] in bekannt):
                continue
            item_id = e["id"]
            gesehen.add(item_id)
            if "deleted" in e:
                self._entferne(bekannt.pop(item_id, None), bericht)
                continue

            eltern = e.get("parentReference", {}).get("id")
            ordner_pfad = self._ordner_pfad(ordner, eltern)
            if ordner_pfad is None:
                bericht.fehler.append(f"{e.get('name')}: Ordnerpfad nicht ermittelbar")
                continue
            sp_pfad = f"/{ordner_pfad}/{e['name']}" if ordner_pfad else f"/{e['name']}"
            grund = self._relevant(e["name"], e.get("size", 0))
            if grund or not self._im_bereich(sp_pfad):
                if item_id in bekannt:
                    self._entferne(bekannt.pop(item_id), bericht)
                elif grund and self._im_bereich(sp_pfad):
                    bericht.uebersprungen.append(f"{sp_pfad}: {grund}")
                continue

            ziel = dokument.ziel_pfad(self.basis, self.name, sp_pfad)
            alt = bekannt.pop(item_id, None)
            meta = {
                "titel": Path(e["name"]).stem,
                "quelle": e.get("webUrl"),
                "sharepoint_pfad": sp_pfad,
                "sharepoint_quelle": self.name,
                "sharepoint_id": item_id,
                "sharepoint_drive_id": drive_id,
                "sharepoint_eltern_id": eltern,
                "ctag": e.get("cTag"),
                "dateityp": Path(e["name"]).suffix.lower().lstrip("."),
                "geaendert_am": e.get("lastModifiedDateTime"),
                "geaendert_von": ((e.get("lastModifiedBy") or {}).get("user") or {}).get(
                    "displayName"
                ),
                "abgeglichen_am": _jetzt(),
            }
            rel = str(ziel.relative_to(self.basis))

            if alt and alt[1].get("ctag") == e.get("cTag"):
                # Inhalt unverändert – höchstens Name/Ort/Metadaten nachziehen
                alt_pfad, alt_meta, text = alt
                if alt_pfad != ziel:
                    meta["abgeglichen_am"] = alt_meta.get("abgeglichen_am", meta["abgeglichen_am"])
                    dokument.schreibe(ziel, meta, text)
                    alt_pfad.unlink()
                    bericht.verschoben.append(f"{alt_pfad.relative_to(self.basis)} → {rel}")
                continue

            try:
                inhalt = self.client.lade_inhalt(drive_id, item_id)
                text = nach_markdown(e["name"], inhalt)
            except Exception as fehler:  # noqa: BLE001 – ein Dokument darf den Lauf nicht abbrechen
                log.exception("Fehler bei %s", sp_pfad)
                bericht.fehler.append(f"{sp_pfad}: {fehler}")
                if alt:
                    bekannt[item_id] = alt  # alten Stand behalten
                continue

            dokument.schreibe(ziel, meta, text)
            if alt and alt[0] != ziel:
                alt[0].unlink()
            (bericht.aktualisiert if alt else bericht.neu).append(rel)

        # 4. Dokumente nachführen, deren Ordner umbenannt/verschoben wurde
        for item_id, (pfad, meta, text) in list(bekannt.items()):
            if item_id in gesehen:
                continue
            if vollabgleich:
                # Im Vollabgleich nicht mehr gemeldet => existiert nicht mehr
                self._entferne(bekannt.pop(item_id), bericht)
                continue
            ordner_pfad = self._ordner_pfad(ordner, meta.get("sharepoint_eltern_id"))
            if ordner_pfad is None:
                # Elternordner gelöscht => Datei mit gelöscht
                self._entferne(bekannt.pop(item_id), bericht)
                continue
            name = Path(meta["sharepoint_pfad"]).name
            sp_pfad = f"/{ordner_pfad}/{name}" if ordner_pfad else f"/{name}"
            if sp_pfad == meta["sharepoint_pfad"]:
                continue
            if not self._im_bereich(sp_pfad):
                self._entferne(bekannt.pop(item_id), bericht)
                continue
            ziel = dokument.ziel_pfad(self.basis, self.name, sp_pfad)
            meta["sharepoint_pfad"] = sp_pfad
            dokument.schreibe(ziel, meta, text)
            if pfad != ziel:
                pfad.unlink()
            bericht.verschoben.append(
                f"{pfad.relative_to(self.basis)} → {ziel.relative_to(self.basis)}"
            )

        self._raeume_leere_ordner(quell_dir)
        self._speichere_zustand({"drive_id": drive_id, "delta_link": neuer_link, "ordner": ordner})

    def _entferne(self, alt, bericht: Bericht) -> None:
        if not alt:
            return
        pfad = alt[0]
        if pfad.exists():
            pfad.unlink()
        bericht.geloescht.append(str(pfad.relative_to(self.basis)))

    @staticmethod
    def _raeume_leere_ordner(wurzel: Path) -> None:
        if not wurzel.exists():
            return
        for d in sorted((p for p in wurzel.rglob("*") if p.is_dir()), reverse=True):
            if not any(d.iterdir()):
                d.rmdir()
