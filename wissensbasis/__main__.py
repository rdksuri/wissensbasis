"""Kommandozeile.

  python -m wissensbasis sync [--voll]   SharePoint abgleichen und Index bauen
  python -m wissensbasis import-ordner   lokal synchronisierte Ordner importieren
  python -m wissensbasis index           nur Index aus wissen/ neu bauen

Quellen mit `lokaler_pfad` in der Konfiguration werden per import-ordner
eingelesen, alle anderen per sync über Microsoft Graph.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import yaml

from .index import baue_index

WURZEL = Path(__file__).resolve().parent.parent


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="wissensbasis")
    p.add_argument("befehl", choices=["sync", "import-ordner", "index"])
    p.add_argument("--voll", action="store_true", help="Vollabgleich statt Delta")
    p.add_argument("--quelle", help="nur diese Quelle verarbeiten (Name aus der Konfiguration)")
    p.add_argument("--config", default=str(WURZEL / "config" / "sharepoint.yaml"))
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    basis = WURZEL / "wissen"
    max_zeichen = int((config.get("chunks") or {}).get("max_zeichen", 1500))

    quellen = [q for q in config["quellen"] if not args.quelle or q["name"] == args.quelle]
    if args.quelle and not quellen:
        p.error(f"Quelle '{args.quelle}' steht nicht in {args.config}")

    fehler = False
    bericht = None
    if args.befehl == "import-ordner":
        from .ordner_import import OrdnerImport
        from .sync import Bericht

        bericht = Bericht()
        lokale = [q for q in quellen if q.get("lokaler_pfad")]
        if not lokale:
            p.error("Keine Quelle mit 'lokaler_pfad' in der Konfiguration")
        for quelle in lokale:
            logging.info("Quelle %s ← %s", quelle["name"], quelle["lokaler_pfad"])
            OrdnerImport(quelle, config, basis).ausfuehren(bericht)
    elif args.befehl == "sync":
        from .graph import GraphClient
        from .sync import Abgleich, Bericht

        graph_quellen = [q for q in quellen if not q.get("lokaler_pfad")]
        bericht = Bericht()
        if not graph_quellen:
            logging.info("Keine Quellen für den Graph-Abgleich (alle per lokaler_pfad).")
        else:
            client = GraphClient(os.environ["AZURE_TENANT_ID"], os.environ["AZURE_CLIENT_ID"])
        for quelle in graph_quellen:
            drive_id = client.finde_drive(quelle["hostname"], quelle["site_pfad"], quelle["bibliothek"])
            logging.info("Quelle %s → Drive %s", quelle["name"], drive_id)
            Abgleich(client, quelle, config, basis, WURZEL / "state").ausfuehren(
                drive_id, bericht, voll=args.voll
            )

    if bericht is not None:
        zusammenfassung = bericht.als_markdown()
        print(zusammenfassung)
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
                f.write(zusammenfassung + "\n")
        fehler = bool(bericht.fehler)

    docs, chunks = baue_index(basis, WURZEL / "index", max_zeichen)
    logging.info("Index: %d Dokumente, %d Abschnitte", docs, chunks)
    if fehler:
        # Einzelne Dokumentfehler brechen den Lauf nicht ab, werden aber gemeldet.
        praefix = "::warning::" if os.environ.get("GITHUB_ACTIONS") else "WARNUNG: "
        print(praefix + "Einzelne Dokumente konnten nicht verarbeitet werden – siehe Zusammenfassung.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
