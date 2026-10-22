# Import vom PC (OneDrive-Synchronisation)

Variante ohne App-Registrierung: Die SharePoint-Bibliothek wird mit deinem
eigenen Konto auf den PC synchronisiert, ein Skript wandelt sie regelmässig
in die Wissensbasis um. Läuft nur, solange der PC an ist.

## 1. Einmalig: Bibliothek synchronisieren

1. Bibliothek im Browser öffnen, z. B.
   `https://ksur.sharepoint.com/sites/DLS/Shared Documents`.
2. Oben auf **Synchronisieren** klicken und im OneDrive-Client bestätigen.
   Tipp: Nur die benötigten Ordner synchronisieren (Rechtsklick auf den
   Ordner → *Verknüpfung zu „Meine Dateien“ hinzufügen* bzw. in den
   OneDrive-Einstellungen *Ordner auswählen*).
3. Im Explorer erscheint ein Ordner wie
   `C:\Users\<NAME>\ksur\DLS - Dokumente`. Diesen Pfad notieren.

**Speicherplatz:** Mit „Dateien bei Bedarf“ (Standard) liegen nur Platzhalter
auf der Platte. Der Import lädt eine Datei nur, wenn sie neu oder geändert
ist, und setzt sie danach wieder auf „Nur online verfügbar“. Dauerhaft
belegt nur der umgewandelte Text Platz. Dateien, die du selbst mit „Immer
auf diesem Gerät behalten“ markiert hast, bleiben unverändert.

## 2. Einmalig: Python und Repository

```powershell
winget install Python.Python.3.12 Git.Git
git clone https://github.com/rdksuri/wissensbasis.git
cd wissensbasis
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

## 3. Konfiguration

In `config/sharepoint.yaml` bei der Quelle `dls` die beiden Zeilen
einkommentieren und anpassen:

```yaml
    lokaler_pfad: 'C:\Users\NAME\ksur\DLS - Dokumente'
    web_basis: https://ksur.sharepoint.com/sites/DLS/Shared Documents
```

`web_basis` ist die Browser-Adresse der Bibliothek (ohne `/Forms/…`); daraus
entstehen die Links zum Original, die der Chatbot als Quelle anzeigt.

## 4. Testlauf

```powershell
.venv\Scripts\python -m wissensbasis import-ordner
```

Die Zusammenfassung zeigt neue, aktualisierte, gelöschte und übersprungene
Dateien sowie Fehler. Ergebnis: `wissen\dls\…` und `index\`.

## 5. Regelmässig ausführen (Aufgabenplanung)

Stündlich werktags von 7 bis 18 Uhr, mit Hochladen zu GitHub:

```powershell
$repo = (Get-Location).Path
$aktion = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$repo\skripte\import.ps1`" -Push"
$ausloeser = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 7am
$ausloeser.Repetition = (New-ScheduledTaskTrigger -Once -At 7am `
  -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Hours 11)).Repetition
Register-ScheduledTask -TaskName "Wissensbasis-Import" -Action $aktion -Trigger $ausloeser
```

Protokoll: `import.log` im Repository-Ordner. Ohne `-Push` bleibt alles
lokal (z. B. wenn der Chatbot auf demselben PC läuft).

> **Achtung:** Das Repository `rdksuri/wissensbasis` ist öffentlich. Mit
> `-Push` sind die Inhalte für alle im Internet lesbar und bleiben in der
> Git-Historie. Vorher klären, ob das zulässig ist, oder das Repository auf
> privat stellen.

## Verhalten im Detail

| Situation | Ergebnis |
|---|---|
| Datei neu oder geändert (Grösse/Änderungszeit) | wird gelesen und umgewandelt |
| Datei unverändert | wird nicht angefasst, nichts wird heruntergeladen |
| Datei gelöscht, verschoben oder umbenannt | altes Dokument wird entfernt (bei Verschieben/Umbenennen neu angelegt) |
| `~$…`-Dateien, versteckte Ordner, nicht konfigurierte Dateitypen | ignoriert |
| Ordner leer, aber Wissensbasis nicht (Synchronisation pausiert?) | **Abbruch ohne Löschen** |
| Ordner nicht vorhanden | Abbruch mit Fehlermeldung |

SharePoint-**Listen** (z. B. Prozessdaten) werden nicht synchronisiert. Sie
lassen sich in SharePoint über *Exportieren → CSV* bzw. *Excel* als Datei in
den synchronisierten Ordner legen; `.csv` und `.xlsx` werden mit importiert.

## Quellen

- Microsoft, *SharePoint-Dateien mit dem Computer synchronisieren*:
  <https://support.microsoft.com/office/sync-sharepoint-and-teams-files-with-your-computer-6de9ede8-5b6e-4503-80b2-6190f3354a88>
- Microsoft, *Dateien bei Bedarf*:
  <https://support.microsoft.com/office/save-disk-space-with-onedrive-files-on-demand-for-windows-0e6860d3-d9f3-4971-b321-7092438fb38e>
- Microsoft, *Dateiattribute* (`RECALL_ON_DATA_ACCESS`, `PINNED`):
  <https://learn.microsoft.com/windows/win32/fileio/file-attribute-constants>
- Microsoft, `attrib`: <https://learn.microsoft.com/windows-server/administration/windows-commands/attrib>
- Microsoft, `Register-ScheduledTask`:
  <https://learn.microsoft.com/powershell/module/scheduledtasks/register-scheduledtask>
- Microsoft, *Liste nach CSV exportieren*:
  <https://support.microsoft.com/office/export-to-excel-from-sharepoint-or-lists-bc3d6e1b-9a4c-4c6b-b6f6-a7c3ef8e7e43>
