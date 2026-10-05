import json
from pathlib import Path

import pytest

from wissensbasis import dokument
from wissensbasis.chunks import zerlege
from wissensbasis.graph import DeltaAbgelaufen
from wissensbasis.index import baue_index
from wissensbasis.sync import Abgleich, Bericht

CONFIG = {"dateitypen": [".md", ".txt", ".docx"], "max_groesse_mb": 1}


class FakeGraph:
    """Simuliert Delta-Antworten: jede Runde ist eine Liste von Einträgen."""

    def __init__(self):
        self.runden: list[list[dict]] = []
        self.inhalte: dict[str, bytes] = {}
        self.abgelaufen = False
        self.voll: list[dict] = []

    def delta(self, drive_id, link):
        if link is None:
            return list(self.voll), "link-0"
        if self.abgelaufen:
            self.abgelaufen = False
            raise DeltaAbgelaufen(link)
        nr = int(link.split("-")[1])
        return self.runden[nr], f"link-{nr + 1}"

    def lade_inhalt(self, drive_id, item_id):
        return self.inhalte[item_id]


def root():
    return {"id": "R", "root": {}, "folder": {}}


def ordner(i, name, eltern="R"):
    return {"id": i, "name": name, "folder": {}, "parentReference": {"id": eltern}}


def datei(i, name, eltern="R", ctag="c1", size=10):
    return {
        "id": i, "name": name, "file": {}, "size": size, "cTag": ctag,
        "parentReference": {"id": eltern}, "webUrl": f"https://sp/{name}",
        "lastModifiedDateTime": "2026-10-01T10:00:00Z",
        "lastModifiedBy": {"user": {"displayName": "Erika Muster"}},
    }


@pytest.fixture
def umgebung(tmp_path):
    g = FakeGraph()
    basis = tmp_path / "wissen"
    quelle = {"name": "team", "ordner": []}

    def lauf(voll=False, quelle=quelle):
        b = Bericht()
        Abgleich(g, quelle, CONFIG, basis, tmp_path / "state").ausfuehren("D", b, voll=voll)
        return b

    return g, basis, lauf


def dateien(basis: Path):
    return sorted(p.relative_to(basis).as_posix() for p in basis.rglob("*.md"))


def test_erstabgleich_und_frontmatter(umgebung):
    g, basis, lauf = umgebung
    g.voll = [root(), ordner("F1", "Richtlinien"), datei("A", "Urlaub.md", "F1"),
              datei("B", "bild.png"), datei("C", "~$Urlaub.docx", "F1")]
    g.inhalte["A"] = "# Urlaub\n\n30 Tage.".encode()
    b = lauf()
    assert dateien(basis) == ["team/Richtlinien/Urlaub.md.md"]
    meta, text = dokument.lese(basis / "team/Richtlinien/Urlaub.md.md")
    assert meta["quelle"] == "https://sp/Urlaub.md"
    assert meta["sharepoint_pfad"] == "/Richtlinien/Urlaub.md"
    assert meta["geaendert_von"] == "Erika Muster"
    assert "30 Tage." in text
    assert b.neu == ["team/Richtlinien/Urlaub.md.md"]
    assert len(b.uebersprungen) == 2


def test_aenderung_umbenennung_loeschung(umgebung):
    g, basis, lauf = umgebung
    g.voll = [root(), ordner("F1", "Alt"), datei("A", "a.txt", "F1"), datei("B", "b.txt")]
    g.inhalte.update({"A": b"eins", "B": b"zwei"})
    lauf()

    # Runde 0: Ordner umbenannt (Datei A selbst nicht gemeldet), B geändert
    g.runden.append([ordner("F1", "Neu"), datei("B", "b.txt", ctag="c2")])
    g.inhalte["B"] = b"zwei neu"
    b = lauf()
    assert dateien(basis) == ["team/Neu/a.txt.md", "team/b.txt.md"]
    assert b.verschoben and b.aktualisiert == ["team/b.txt.md"]
    assert "zwei neu" in dokument.lese(basis / "team/b.txt.md")[1]
    assert dokument.lese(basis / "team/Neu/a.txt.md")[0]["sharepoint_pfad"] == "/Neu/a.txt"

    # Runde 1: B gelöscht (Delta liefert dann oft keine file-Facette)
    g.runden.append([{"id": "B", "deleted": {}}])
    b = lauf()
    assert dateien(basis) == ["team/Neu/a.txt.md"]
    assert b.geloescht == ["team/b.txt.md"]

    # Runde 2: Ordner gelöscht -> enthaltene Datei verschwindet
    g.runden.append([{"id": "F1", "folder": {}, "deleted": {}}])
    lauf()
    assert dateien(basis) == []
    assert not (basis / "team" / "Neu").exists()


def test_abgelaufener_deltalink_fuehrt_zu_vollabgleich(umgebung):
    g, basis, lauf = umgebung
    g.voll = [root(), datei("A", "a.txt"), datei("B", "b.txt")]
    g.inhalte.update({"A": b"a", "B": b"b"})
    lauf()
    g.abgelaufen = True
    g.runden.append([])
    g.voll = [root(), datei("A", "a.txt")]  # B existiert nicht mehr
    b = lauf()
    assert dateien(basis) == ["team/a.txt.md"]
    assert b.geloescht == ["team/b.txt.md"]


def test_ordnerfilter(umgebung):
    g, basis, lauf = umgebung
    quelle = {"name": "team", "ordner": ["/Öffentlich"]}
    g.voll = [root(), ordner("F1", "Öffentlich"), ordner("F2", "Intern"),
              datei("A", "a.txt", "F1"), datei("B", "b.txt", "F2")]
    g.inhalte.update({"A": b"a", "B": b"b"})
    lauf(quelle=quelle)
    assert dateien(basis) == ["team/Öffentlich/a.txt.md"]
    # A wird nach "Intern" verschoben -> fällt aus dem Bereich
    g.runden.append([datei("A", "a.txt", "F2")])
    lauf(quelle=quelle)
    assert dateien(basis) == []


def test_fehler_bei_konvertierung_behaelt_alten_stand(umgebung):
    g, basis, lauf = umgebung
    g.voll = [root(), datei("A", "a.txt")]
    g.inhalte["A"] = b"alt"
    lauf()
    g.runden.append([datei("A", "a.txt", ctag="c2")])
    del g.inhalte["A"]
    b = lauf()
    assert b.fehler and "alt" in dokument.lese(basis / "team/a.txt.md")[1]


def test_zerlege_und_index(tmp_path):
    text = "Einleitung\n\n# Kapitel 1\n\nText eins.\n\n## Unterpunkt\n\n" + ("Satz. " * 400)
    teile = zerlege(text, max_zeichen=500)
    assert teile[0]["ueberschrift"] == ""
    assert teile[1]["ueberschrift"] == "Kapitel 1"
    assert all(t["ueberschrift"] == "Kapitel 1 > Unterpunkt" for t in teile[2:])
    assert all(len(t["text"]) <= 500 for t in teile)

    basis = tmp_path / "wissen"
    dokument.schreibe(basis / "q/x.md.md", {"titel": "x", "sharepoint_id": "X", "quelle": "u"}, text)
    docs, chunks = baue_index(basis, tmp_path / "index", 500)
    assert docs == 1 and chunks == len(teile)
    zeile = json.loads((tmp_path / "index/chunks.jsonl").read_text().splitlines()[1])
    assert zeile["id"] == "X#1" and zeile["datei"] == "wissen/q/x.md.md"


def test_sauberer_name():
    assert dokument.sauberer_name('Bericht: "Q3"?.docx') == "Bericht_ _Q3__.docx"
    assert dokument.ziel_pfad(Path("w"), "q", "/A/Ä b.pdf") == Path("w/q/A/Ä b.pdf.md")
