import httpx


class GitLabClient:
    """Schmaler Client für die GitLab-REST-API (v4). Nur was der Sync braucht."""

    def __init__(self, url: str, token: str):
        self.basis = url.rstrip("/") + "/api/v4"
        self.headers = {"PRIVATE-TOKEN": token}

    def issues(self, projekt_id: int) -> list[dict]:
        """Alle Issues eines Projekts (offen und zu), über alle Seiten."""
        alle: list[dict] = []
        seite = 1
        while True:
            antwort = httpx.get(
                f"{self.basis}/projects/{projekt_id}/issues",
                headers=self.headers,
                params={"state": "all", "per_page": 100, "page": seite},
                timeout=20,
            )
            antwort.raise_for_status()
            daten = antwort.json()
            alle.extend(daten)
            if len(daten) < 100:
                return alle
            seite += 1

    def issue_aktualisieren(self, projekt_id: int, issue_iid: int, **felder) -> None:
        antwort = httpx.put(
            f"{self.basis}/projects/{projekt_id}/issues/{issue_iid}",
            headers=self.headers,
            json=felder,
            timeout=20,
        )
        antwort.raise_for_status()
