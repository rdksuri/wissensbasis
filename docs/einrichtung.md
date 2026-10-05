# Einrichtung

Einmalig nötig, damit der Workflow lesend auf SharePoint zugreifen darf.
Benötigt werden Administratorrechte in Microsoft Entra ID (bzw. die Mithilfe
der IT) sowie Admin-Rechte am GitHub-Repository.

## 1. App-Registrierung in Microsoft Entra ID

1. Entra Admin Center → *Identität* → *Anwendungen* → *App-Registrierungen* →
   *Neue Registrierung*, Name z. B. `wissensbasis-sync`, nur dieser Mandant.
2. **Verzeichnis-(Mandanten-)ID** und **Anwendungs-(Client-)ID** notieren.
3. *API-Berechtigungen* → *Microsoft Graph* → *Anwendungsberechtigungen*:
   - **empfohlen:** `Sites.Selected` (Zugriff nur auf ausdrücklich freigegebene Sites), oder
   - einfacher, aber weitreichend: `Sites.Read.All` (alle Sites des Mandanten lesbar).
4. *Administratorzustimmung erteilen*.

Quelle: <https://learn.microsoft.com/graph/auth-v2-service>

### Nur bei `Sites.Selected`: Site freigeben

Ein Administrator (mit `Sites.FullControl.All`, z. B. über Graph Explorer)
erteilt der App Leserechte für die gewünschte Site:

```http
GET  https://graph.microsoft.com/v1.0/sites/contoso.sharepoint.com:/sites/Wissen
POST https://graph.microsoft.com/v1.0/sites/{site-id}/permissions
Content-Type: application/json

{
  "roles": ["read"],
  "grantedToIdentities": [
    { "application": { "id": "<Client-ID>", "displayName": "wissensbasis-sync" } }
  ]
}
```

Quellen: <https://learn.microsoft.com/graph/permissions-selected-overview>,
<https://learn.microsoft.com/graph/api/site-post-permissions>

## 2. Anmeldung des Workflows – eine Variante wählen

**A) Ohne Secret über GitHub-OIDC (empfohlen).** Kein Passwort, das ablaufen
oder abfliessen kann.

App-Registrierung → *Zertifikate & Geheimnisse* → *Verbundanmeldeinformationen*
→ *Hinzufügen* → Szenario *GitHub Actions, die Azure-Ressourcen bereitstellen*:

| Feld | Wert |
|---|---|
| Organisation | `rdksuri` |
| Repository | `wissensbasis` |
| Entitätstyp | Branch |
| Branch | Standard-Branch des Repos (z. B. `main`) |

Quelle: <https://learn.microsoft.com/entra/workload-id/workload-identity-federation-create-trust>

**B) Mit Client-Secret.** *Zertifikate & Geheimnisse* → *Neuer geheimer
Clientschlüssel*; Ablaufdatum notieren und rechtzeitig erneuern.

## 3. GitHub konfigurieren

Repository → *Settings* → *Secrets and variables* → *Actions*:

| Art | Name | Wert |
|---|---|---|
| Variable | `AZURE_TENANT_ID` | Verzeichnis-ID |
| Variable | `AZURE_CLIENT_ID` | Client-ID |
| Secret | `AZURE_CLIENT_SECRET` | nur bei Variante B |

Ausserdem unter *Settings* → *Actions* → *General* → *Workflow permissions*
„Read and write permissions“ zulassen, damit der Workflow committen darf.

## 4. Quellen eintragen und testen

`config/sharepoint.yaml` anpassen (Hostname, Site-Pfad, Bibliothek, optional
Ordner). Danach *Actions* → *SharePoint-Abgleich* → *Run workflow*. Die
Zusammenfassung des Laufs zeigt neue, geänderte, gelöschte und übersprungene
Dateien sowie Fehler.

Hinweis: Geplante Workflows laufen nur auf dem Standard-Branch und werden von
GitHub nach 60 Tagen ohne Repository-Aktivität automatisch pausiert. Da jeder
Abgleich mit Änderungen committet, tritt das in der Praxis selten ein.
Quelle: <https://docs.github.com/actions/managing-workflow-runs-and-deployments/managing-workflow-runs/disabling-and-enabling-a-workflow>
