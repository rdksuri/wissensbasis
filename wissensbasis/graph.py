"""Schlanker Microsoft-Graph-Client für den Abgleich von SharePoint-Bibliotheken.

Authentifizierung über App-Registrierung (Client-Credentials-Flow):
- mit AZURE_CLIENT_SECRET, oder
- ohne Secret über GitHub-OIDC (Workload Identity Federation), wenn der
  Workflow `permissions: id-token: write` hat.

Quellen:
- https://learn.microsoft.com/entra/identity-platform/v2-oauth2-client-creds-grant-flow
- https://learn.microsoft.com/entra/workload-id/workload-identity-federation
- https://learn.microsoft.com/graph/api/driveitem-delta
"""

from __future__ import annotations

import os
import time
from urllib.parse import quote

import requests

GRAPH = "https://graph.microsoft.com/v1.0"
SCOPE = "https://graph.microsoft.com/.default"


class DeltaAbgelaufen(Exception):
    """Der gespeicherte deltaLink ist ungültig (HTTP 410) – Vollabgleich nötig."""


def _github_oidc_token() -> str:
    url = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL")
    token = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
    if not url or not token:
        raise RuntimeError(
            "Weder AZURE_CLIENT_SECRET gesetzt noch GitHub-OIDC verfügbar "
            "(Workflow braucht 'permissions: id-token: write')."
        )
    r = requests.get(
        url + "&audience=api://AzureADTokenExchange",
        headers={"Authorization": f"bearer {token}"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["value"]


def hole_token(tenant_id: str, client_id: str) -> str:
    daten = {"client_id": client_id, "scope": SCOPE, "grant_type": "client_credentials"}
    secret = os.environ.get("AZURE_CLIENT_SECRET")
    if secret:
        daten["client_secret"] = secret
    else:
        daten["client_assertion_type"] = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
        daten["client_assertion"] = _github_oidc_token()
    r = requests.post(
        f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
        data=daten,
        timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Token-Anfrage fehlgeschlagen: {r.status_code} {r.text}")
    return r.json()["access_token"]


class GraphClient:
    def __init__(self, tenant_id: str, client_id: str):
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._token = hole_token(tenant_id, client_id)
        self._session = requests.Session()

    def _get(self, url: str, **kwargs) -> requests.Response:
        if not url.startswith("http"):
            url = GRAPH + url
        for versuch in range(6):
            r = self._session.get(
                url, headers={"Authorization": f"Bearer {self._token}"}, timeout=120, **kwargs
            )
            if r.status_code == 401 and versuch == 0:
                self._token = hole_token(self._tenant_id, self._client_id)
                continue
            if r.status_code in (429, 503, 504):
                time.sleep(int(r.headers.get("Retry-After", 2 ** versuch)))
                continue
            return r
        return r

    def _json(self, url: str) -> dict:
        r = self._get(url)
        if r.status_code == 410:
            raise DeltaAbgelaufen(url)
        r.raise_for_status()
        return r.json()

    def finde_drive(self, hostname: str, site_pfad: str, bibliothek: str) -> str:
        site = self._json(f"/sites/{hostname}:{quote(site_pfad)}")
        drives = self._json(f"/sites/{site['id']}/drives")["value"]
        gesucht = bibliothek.strip().lower()
        for d in drives:
            url_name = requests.utils.unquote(d.get("webUrl", "").rstrip("/").rsplit("/", 1)[-1])
            if gesucht in (d.get("name", "").lower(), url_name.lower()):
                return d["id"]
        namen = ", ".join(d.get("name", "?") for d in drives)
        raise RuntimeError(f"Bibliothek '{bibliothek}' nicht gefunden. Vorhanden: {namen}")

    def delta(self, drive_id: str, delta_link: str | None) -> tuple[list[dict], str]:
        """Liefert alle Änderungen seit delta_link (oder alles, wenn None) und den neuen deltaLink."""
        url = delta_link or f"/drives/{drive_id}/root/delta"
        eintraege: list[dict] = []
        while True:
            seite = self._json(url)
            eintraege.extend(seite.get("value", []))
            if "@odata.nextLink" in seite:
                url = seite["@odata.nextLink"]
            else:
                return eintraege, seite["@odata.deltaLink"]

    def lade_inhalt(self, drive_id: str, item_id: str) -> bytes:
        r = self._get(f"/drives/{drive_id}/items/{item_id}/content")
        r.raise_for_status()
        return r.content
