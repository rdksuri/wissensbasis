"""Import aus einem lokal synchronisierten SharePoint-Ordner (OneDrive-Client).

Alternative zum Graph-Abgleich, wenn keine App-Registrierung verfügbar ist:
Die SharePoint-Bibliothek wird mit „Synchronisieren“ auf den PC geholt, dieser
Befehl wandelt den Ordner in wissen/ um.

Speicherplatz: Mit „Dateien bei Bedarf“ liegen zunächst nur Platzhalter auf
der Platte. Zum Umwandeln muss eine Datei gelesen und damit heruntergeladen
werden. Danach wird sie wieder auf „Nur online verfügbar“ gesetzt – aber nur,
wenn sie vorher schon nur online war; von Hand lokal gehaltene Dateien bleiben
unangetastet.

Quellen:
- https://support.microsoft.com/office/save-disk-space-with-onedrive-files-on-demand-for-windows-0e6860d3-d9f3-4971-b321-7092438fb38e
- https://support.microsoft.com/office/save-disk-space-with-onedrive-files-on-demand-for-mac-529f6d53-e572-4922-a585-e7a318c135f0
- macOS SF_DATALESS: https://github.com/apple-oss-distributions/xnu/blob/main/bsd/sys/stat.h
- https://learn.microsoft.com/windows/win32/fileio/file-attribute-constants
- https://learn.microsoft.com/windows-server/administration/windows-commands/attrib
"""

from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from . import dokument
from .konvertierung import nach_markdown
from .sync import Abgleich, Bericht, _jetzt

log = logging.getLogger(__name__)

# Windows-Dateiattribute für Cloud-Platzhalter
RECALL_ON_DATA_ACCESS = 0x00400000  # Inhalt liegt nicht lokal
PINNED = 0x00080000                 # „Immer auf diesem Gerät behalten“
# macOS (File Provider): Datei ist ein Platzhalter ohne lokalen Inhalt
SF_DATALESS = 0x40000000

_mac_freigabe_aktiv = True


def nur_online(pfad: Path) -> bool:
    """True, wenn die Datei ein reiner Cloud-Platzhalter ist (Windows und macOS)."""
    st = os.stat(pfad)
    attribute = getattr(st, "st_file_attributes", 0)
    if attribute:
        return bool(attribute & RECALL_ON_DATA_ACCESS) and not attribute & PINNED
    return bool(getattr(st, "st_flags", 0) & SF_DATALESS)


def speicher_freigeben(pfad: Path) -> None:
    """Setzt die Datei wieder auf „Nur online verfügbar“."""
    global _mac_freigabe_aktiv
    if sys.platform == "win32":
        subprocess.run(["attrib", "+U", "-P", str(pfad)], check=False, capture_output=True)
    elif sys.platform == "darwin" and _mac_freigabe_aktiv:
        # fileproviderctl ist nicht offiziell dokumentiert: schlägt es fehl,
        # einmal warnen und für den Rest des Laufs nicht weiter versuchen.
        try:
            r = subprocess.run(["fileproviderctl", "evict", str(pfad)],
                               check=False, capture_output=True, text=True, timeout=60)
            fehler = r.returncode != 0 and (r.stderr or r.stdout).strip()
        except (OSError, subprocess.TimeoutExpired) as e:
            fehler = str(e)
        if fehler:
            _mac_freigabe_aktiv = False
            log.warning(
                "Speicher konnte nicht automatisch freigegeben werden (%s). Gelesene Dateien "
                "bleiben lokal; im Finder per Rechtsklick → „Speicherplatz freigeben“ "
                "wieder auf nur online setzen.", fehler)


def dokument_id(quelle: str, rel_pfad: str) -> str:
    """Stabile ID aus Quelle und Pfad (lokal gibt es keine SharePoint-ID)."""
    return "lokal-" + hashlib.sha1(f"{quelle}:{rel_pfad}".encode()).hexdigest()[:20]


def _stand(stat: os.stat_result) -> str:
    return f"{stat.st_size}:{int(stat.st_mtime)}"


class OrdnerImport:
    def __init__(self, quelle: dict, config: dict, basis: Path,
                 ist_nur_online=nur_online, freigeben=speicher_freigeben):
        self.name = quelle["name"]
        self.wurzel = Path(quelle["lokaler_pfad"]).expanduser()
        # safe enthält "%", damit bereits kodierte Links (…/Shared%20Documents) bleiben
        self.web_basis = quote((quelle.get("web_basis") or "").rstrip("/"), safe=":/%")
        self.basis = basis
        self.endungen = {e.lower() for e in config.get("dateitypen", [])}
        self.max_bytes = int(config.get("max_groesse_mb", 50)) * 1024 * 1024
        self.ordner_filter = ["/" + o.strip("/") for o in quelle.get("ordner") or [] if o.strip("/")]
        self._ist_nur_online = ist_nur_online
        self._freigeben = freigeben

    def _im_bereich(self, sp_pfad: str) -> bool:
        return not self.ordner_filter or any(
            sp_pfad == o or sp_pfad.startswith(o + "/") for o in self.ordner_filter
        )

    def _url(self, sp_pfad: str) -> str | None:
        return f"{self.web_basis}{quote(sp_pfad)}" if self.web_basis else None

    def _dateien(self):
        """Dateien Ordner für Ordner liefern (statt erst alles aufzulisten),
        damit bei grossen OneDrive-Ordnern sofort Fortschritt sichtbar ist.
        Versteckte Ordner werden gar nicht erst betreten."""
        for ordner, unterordner, dateien in os.walk(self.wurzel):
            unterordner[:] = sorted(u for u in unterordner if not u.startswith("."))
            rel = Path(ordner).relative_to(self.wurzel).as_posix()
            if rel != "." and self.ordner_filter and not any(
                ("/" + rel).startswith(o) or o.startswith("/" + rel + "/") for o in self.ordner_filter
            ):
                unterordner[:] = []
                continue
            log.info("Durchsuche %s (%d Dateien)", "/" if rel == "." else "/" + rel, len(dateien))
            for name in sorted(dateien):
                if not name.startswith("."):
                    yield Path(ordner) / name

    def ausfuehren(self, bericht: Bericht) -> None:
        if not self.wurzel.is_dir():
            raise FileNotFoundError(f"Ordner für Quelle '{self.name}' nicht gefunden: {self.wurzel}")

        quell_dir = self.basis / dokument.sauberer_name(self.name)
        bekannt = {}
        if quell_dir.exists():
            for pfad, meta, text in dokument.alle(quell_dir):
                bekannt[meta["sharepoint_id"]] = (pfad, meta, text)

        gesehen: set[str] = set()
        gelesen = 0
        for datei in self._dateien():
            rel = datei.relative_to(self.wurzel).as_posix()
            sp_pfad = "/" + rel
            if datei.name.startswith("~$"):
                continue
            if not self._im_bereich(sp_pfad):
                continue
            endung = datei.suffix.lower()
            stat = datei.stat()  # liest nur Metadaten, lädt nichts herunter
            if self.endungen and endung not in self.endungen:
                continue
            if stat.st_size > self.max_bytes:
                bericht.uebersprungen.append(f"{sp_pfad}: zu gross ({stat.st_size // (1024 * 1024)} MB)")
                continue

            doc_id = dokument_id(self.name, rel)
            gesehen.add(doc_id)
            alt = bekannt.get(doc_id)
            if alt and alt[1].get("lokal_stand") == _stand(stat):
                continue  # unverändert – nichts lesen, nichts herunterladen

            war_nur_online = self._ist_nur_online(datei)
            gelesen += 1
            log.info("[%d] %s %s (%.1f MB)", gelesen,
                     "Lade und wandle um:" if war_nur_online else "Wandle um:",
                     sp_pfad, stat.st_size / 1024 / 1024)
            try:
                text = nach_markdown(datei.name, datei.read_bytes())
            except Exception as fehler:  # noqa: BLE001 – ein Dokument darf den Lauf nicht abbrechen
                log.exception("Fehler bei %s", sp_pfad)
                bericht.fehler.append(f"{sp_pfad}: {fehler}")
                continue
            finally:
                if war_nur_online:
                    self._freigeben(datei)

            meta = {
                "titel": datei.stem,
                "quelle": self._url(sp_pfad),
                "sharepoint_pfad": sp_pfad,
                "sharepoint_quelle": self.name,
                "sharepoint_id": doc_id,
                "lokal_stand": _stand(stat),
                "dateityp": endung.lstrip("."),
                "geaendert_am": datetime.fromtimestamp(stat.st_mtime, timezone.utc)
                .replace(microsecond=0).isoformat(),
                "geaendert_von": None,
                "abgeglichen_am": _jetzt(),
            }
            ziel = dokument.ziel_pfad(self.basis, self.name, sp_pfad)
            dokument.schreibe(ziel, meta, text)
            (bericht.aktualisiert if alt else bericht.neu).append(
                str(ziel.relative_to(self.basis))
            )

        # Schutz: leerer Ordner (Synchronisation pausiert, falsches Laufwerk …)
        # darf nicht die ganze Wissensbasis löschen.
        if bekannt and not gesehen:
            raise RuntimeError(
                f"Im Ordner {self.wurzel} wurden keine passenden Dateien gefunden, "
                f"die Wissensbasis enthält aber {len(bekannt)} Dokumente dieser Quelle. "
                "Abbruch ohne Löschen – bitte OneDrive-Synchronisation prüfen."
            )

        # In SharePoint gelöschte, verschobene oder umbenannte Dateien entfernen
        for doc_id, (pfad, _, _) in bekannt.items():
            if doc_id not in gesehen:
                pfad.unlink(missing_ok=True)
                bericht.geloescht.append(str(pfad.relative_to(self.basis)))

        Abgleich._raeume_leere_ordner(quell_dir)
