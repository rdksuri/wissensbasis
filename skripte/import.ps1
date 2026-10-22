<#
.SYNOPSIS
  Importiert die per OneDrive synchronisierten SharePoint-Ordner in die
  Wissensbasis und lädt die Änderungen optional zu GitHub hoch.

.PARAMETER Push
  Änderungen committen und zu GitHub pushen. ACHTUNG: Ist das Repository
  öffentlich, sind die Inhalte danach für alle im Internet lesbar.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File skripte\import.ps1 -Push
#>
param([switch]$Push)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
$log = Join-Path $repo "import.log"
Start-Transcript -Path $log -Append | Out-Null

try {
    if ($Push) { git pull --ff-only }

    $python = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
    & $python -m wissensbasis import-ordner
    if ($LASTEXITCODE -ne 0) { throw "Import fehlgeschlagen (Exit-Code $LASTEXITCODE)" }

    if ($Push) {
        git add -A wissen index
        git diff --cached --quiet
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Keine Änderungen."
        } else {
            git commit -m "Ordner-Import $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
            git push
        }
    }
} finally {
    Stop-Transcript | Out-Null
}
