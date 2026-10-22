import os
import time

import pytest

from wissensbasis import dokument
from wissensbasis.ordner_import import OrdnerImport, dokument_id
from wissensbasis.sync import Bericht

CONFIG = {"dateitypen": [".md", ".txt"], "max_groesse_mb": 1}


@pytest.fixture
def umgebung(tmp_path):
    quelle_dir = tmp_path / "OneDrive" / "DLS - Dokumente"
    quelle_dir.mkdir(parents=True)
    basis = tmp_path / "wissen"
    platzhalter: set[str] = set()   # simuliert „nur online verfügbar“
    freigegeben: list[str] = []
    quelle = {"name": "dls", "lokaler_pfad": str(quelle_dir),
              "web_basis": "https://ksur.sharepoint.com/sites/DLS/Shared Documents"}

    def lauf(q=None):
        b = Bericht()
        OrdnerImport(
            q or quelle, CONFIG, basis,
            ist_nur_online=lambda p: p.name in platzhalter,
            freigeben=lambda p: freigegeben.append(p.name),
        ).ausfuehren(b)
        return b

    return quelle_dir, basis, lauf, platzhalter, freigegeben


def dateien(basis):
    return sorted(p.relative_to(basis).as_posix() for p in basis.rglob("*.md"))


def schreibe(pfad, text, zeit=None):
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(text, encoding="utf-8")
    if zeit:
        os.utime(pfad, (zeit, zeit))


def test_import_mit_metadaten_und_filtern(umgebung):
    ordner, basis, lauf, *_ = umgebung
    schreibe(ordner / "Prozesse" / "Einkauf Ä.md", "# Einkauf\n\nFreigabe ab 1000 €.")
    schreibe(ordner / "bild.png", "x")
    schreibe(ordner / "~$Entwurf.md", "x")
    schreibe(ordner / ".versteckt" / "a.md", "x")
    b = lauf()
    assert dateien(basis) == ["dls/Prozesse/Einkauf Ä.md.md"]
    meta, text = dokument.lese(basis / "dls/Prozesse/Einkauf Ä.md.md")
    assert meta["quelle"] == (
        "https://ksur.sharepoint.com/sites/DLS/Shared%20Documents/Prozesse/Einkauf%20%C3%84.md"
    )
    assert meta["sharepoint_id"] == dokument_id("dls", "Prozesse/Einkauf Ä.md")
    assert "1000 €" in text and b.neu


def test_unveraenderte_dateien_werden_nicht_gelesen(umgebung, monkeypatch):
    ordner, basis, lauf, *_ = umgebung
    schreibe(ordner / "a.txt", "eins", zeit=1_700_000_000)
    lauf()
    gelesen = []
    from wissensbasis import ordner_import
    original = ordner_import.nach_markdown
    monkeypatch.setattr(ordner_import, "nach_markdown",
                        lambda n, b: gelesen.append(n) or original(n, b))
    b = lauf()
    assert gelesen == [] and not b.hat_aenderungen()

    schreibe(ordner / "a.txt", "zwei!", zeit=1_700_000_100)
    b = lauf()
    assert gelesen == ["a.txt"] and b.aktualisiert == ["dls/a.txt.md"]
    assert "zwei!" in dokument.lese(basis / "dls/a.txt.md")[1]


def test_bereits_kodierte_web_basis(umgebung):
    ordner, basis, lauf, *_ = umgebung
    schreibe(ordner / "a.txt", "a")
    lauf({"name": "dls", "lokaler_pfad": str(ordner),
          "web_basis": "https://ksur.sharepoint.com/sites/DLS/Shared%20Documents/"})
    assert dokument.lese(basis / "dls/a.txt.md")[0]["quelle"] == (
        "https://ksur.sharepoint.com/sites/DLS/Shared%20Documents/a.txt"
    )


def test_speicher_nur_fuer_platzhalter_freigeben(umgebung):
    ordner, basis, lauf, platzhalter, freigegeben = umgebung
    schreibe(ordner / "online.txt", "a")
    schreibe(ordner / "lokal.txt", "b")
    platzhalter.add("online.txt")
    lauf()
    assert freigegeben == ["online.txt"]


def test_loeschen_und_umbenennen(umgebung):
    ordner, basis, lauf, *_ = umgebung
    schreibe(ordner / "a.txt", "a")
    schreibe(ordner / "b.txt", "b")
    lauf()
    (ordner / "a.txt").unlink()
    (ordner / "b.txt").rename(ordner / "c.txt")
    b = lauf()
    assert dateien(basis) == ["dls/c.txt.md"]
    assert sorted(b.geloescht) == ["dls/a.txt.md", "dls/b.txt.md"]


def test_leerer_ordner_loescht_nichts(umgebung):
    ordner, basis, lauf, *_ = umgebung
    schreibe(ordner / "a.txt", "a")
    lauf()
    (ordner / "a.txt").unlink()
    with pytest.raises(RuntimeError, match="Synchronisation"):
        lauf()
    assert dateien(basis) == ["dls/a.txt.md"]


def test_fehlender_ordner(umgebung, tmp_path):
    *_, lauf, _, _ = umgebung
    with pytest.raises(FileNotFoundError):
        lauf({"name": "x", "lokaler_pfad": str(tmp_path / "gibtsnicht")})


def test_platzhalter_erkennung_macos(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from wissensbasis import ordner_import as oi
    f = tmp_path / "a.txt"
    f.write_text("x")
    monkeypatch.setattr(oi.os, "stat", lambda p: SimpleNamespace(st_flags=oi.SF_DATALESS))
    assert oi.nur_online(f)
    monkeypatch.setattr(oi.os, "stat", lambda p: SimpleNamespace(st_flags=0))
    assert not oi.nur_online(f)


def test_mac_freigabe_fehler_nur_einmal(tmp_path, monkeypatch, caplog):
    from types import SimpleNamespace

    from wissensbasis import ordner_import as oi
    aufrufe = []
    monkeypatch.setattr(oi.sys, "platform", "darwin")
    monkeypatch.setattr(oi, "_mac_freigabe_aktiv", True)
    monkeypatch.setattr(oi.subprocess, "run", lambda cmd, **kw: aufrufe.append(cmd)
                        or SimpleNamespace(returncode=1, stderr="unknown command", stdout=""))
    oi.speicher_freigeben(tmp_path / "a")
    oi.speicher_freigeben(tmp_path / "b")
    assert len(aufrufe) == 1 and aufrufe[0][:2] == ["fileproviderctl", "evict"]
    assert "Speicherplatz freigeben" in caplog.text


def test_lokale_config_wird_zusammengefuehrt(tmp_path):
    from wissensbasis.__main__ import lade_config
    (tmp_path / "sharepoint.yaml").write_text(
        "quellen:\n  - name: a\n    web_basis: https://x\n", encoding="utf-8")
    assert "lokaler_pfad" not in lade_config(tmp_path / "sharepoint.yaml")["quellen"][0]
    (tmp_path / "lokal.yaml").write_text(
        "quellen:\n  - name: a\n    lokaler_pfad: ~/OD\n", encoding="utf-8")
    q = lade_config(tmp_path / "sharepoint.yaml")["quellen"][0]
    assert q == {"name": "a", "web_basis": "https://x", "lokaler_pfad": "~/OD"}
