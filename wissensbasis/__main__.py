"""Kommandozeile.

  python -m wissensbasis sync [--voll]   SharePoint abgleichen und Index bauen
  python -m wissensbasis index           nur Index aus wissen/ neu bauen
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
    p.add_argument("befehl", choices=["sync", "index"])
    p.add_argument("--voll", action="store_true", help="Vollabgleich statt Delta")
    p.add_argument("--config", default=str(WURZEL / "config" / "sharepoint.yaml"))
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    basis = WURZEL / "wissen"
    max_zeichen = int((config.get("chunks") or {}).get("max_zeichen", 1500))

    fehler = False
    if args.befehl == "sync":
        from .graph import GraphClient
        from .sync import Abgleich, Bericht

        client = GraphClient(os.environ["AZURE_TENANT_ID"], os.environ["AZURE_CLIENT_ID"])
        bericht = Bericht()
        for quelle in config["quellen"]:
            drive_id = client.finde_drive(quelle["hostname"], quelle["site_pfad"], quelle["bibliothek"])
            logging.info("Quelle %s → Drive %s", quelle["name"], drive_id)
            Abgleich(client, quelle, config, basis, WURZEL / "state").ausfuehren(
                drive_id, bericht, voll=args.voll
            )
        zusammenfassung = bericht.als_markdown()
        print(zusammenfassung)
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
                f.write(zusammenfassung + "\n")
        fehler = bool(bericht.fehler)

    docs, chunks = baue_index(basis, WURZEL / "index", max_zeichen)
    logging.info("Index: %d Dokumente, %d Abschnitte", docs, chunks)
    if fehler:
        # Einzelne Dokumentfehler brechen den Lauf nicht ab, erscheinen aber
        # als Warnung im GitHub-Actions-Protokoll.
        print("::warning::Einzelne Dokumente konnten nicht abgeglichen werden – siehe Zusammenfassung.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
