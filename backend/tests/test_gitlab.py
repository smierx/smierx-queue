from datetime import datetime, timedelta, timezone

import pytest

from app.routers import gitlab as gitlab_router

PROJEKT = 42


def _utc_jetzt() -> datetime:
    # GitLab liefert UTC, die DB-Defaults sind ebenfalls UTC.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class FakeGitLab:
    """Simuliert die GitLab-API in-memory und protokolliert Schreibzugriffe."""

    def __init__(self):
        self._issues: dict[int, dict] = {}
        self.updates: list[dict] = []

    def issue(self, iid, titel, state="opened", labels=None, geaendert=None):
        self._issues[iid] = {
            "iid": iid,
            "title": titel,
            "description": "",
            "state": state,
            "labels": labels or [],
            "updated_at": (geaendert or _utc_jetzt()).isoformat(),
        }

    def issues(self, projekt_id):
        return list(self._issues.values())

    def issue_aktualisieren(self, projekt_id, issue_iid, **felder):
        self.updates.append({"projekt": projekt_id, "iid": issue_iid, **felder})


@pytest.fixture()
def fake(monkeypatch):
    fake = FakeGitLab()
    monkeypatch.setattr(gitlab_router, "client_fuer", lambda verbindung: fake)
    return fake


def _verbinden(client):
    r = client.put(
        "/api/gitlab/connection",
        json={"url": "https://gitlab.example.com", "token": "glpat-x", "projekt_ids": [PROJEKT]},
    )
    assert r.status_code == 200
    return r.json()


def test_verbindung_anlegen_ohne_token_leak(client):
    daten = _verbinden(client)
    assert daten == {"url": "https://gitlab.example.com", "projekt_ids": [PROJEKT]}
    assert "token" not in client.get("/api/gitlab/connection").json()


def test_verbindung_update_behaelt_token(client):
    _verbinden(client)
    r = client.put(
        "/api/gitlab/connection",
        json={"url": "https://gitlab.example.com", "token": "", "projekt_ids": [PROJEKT, 7]},
    )
    assert r.status_code == 200
    assert r.json()["projekt_ids"] == [PROJEKT, 7]


def test_sync_ohne_verbindung_404(client):
    assert client.post("/api/gitlab/sync").status_code == 404


def test_import_offener_issues(client, fake):
    _verbinden(client)
    fake.issue(1, "Pipeline reparieren", labels=["queue::critical", "bug"])
    fake.issue(2, "Doku schreiben")
    fake.issue(3, "Schon zu", state="closed")

    r = client.post("/api/gitlab/sync")
    assert r.status_code == 200
    assert r.json()["importiert"] == 2

    tasks = client.get("/api/tasks").json()
    assert [t["titel"] for t in tasks] == ["Pipeline reparieren", "Doku schreiben"]
    # queue::-Label wird Tag, fremdes Label ("bug") nicht.
    assert tasks[0]["tags"] == ["critical"]

    # Zweiter Sync importiert nichts doppelt.
    assert client.post("/api/gitlab/sync").json()["importiert"] == 0


def test_geschlossenes_issue_archiviert_task(client, fake):
    _verbinden(client)
    fake.issue(1, "Wird erledigt")
    client.post("/api/gitlab/sync")
    assert len(client.get("/api/tasks").json()) == 1

    fake.issue(1, "Wird erledigt", state="closed")
    r = client.post("/api/gitlab/sync")
    assert r.json()["geschlossen"] == 1
    # Raus aus der Queue, aber im Archiv samt Task erhalten.
    assert client.get("/api/tasks").json() == []
    archiv = client.get("/api/tasks", params={"erledigt": "true"}).json()
    assert [t["titel"] for t in archiv] == ["Wird erledigt"]
    assert archiv[0]["erledigt_am"] is not None


def test_reopened_issue_kommt_zurueck_in_die_queue(client, fake):
    _verbinden(client)
    fake.issue(1, "Kommt wieder")
    client.post("/api/gitlab/sync")
    fake.issue(1, "Kommt wieder", state="closed")
    client.post("/api/gitlab/sync")
    assert client.get("/api/tasks").json() == []

    fake.issue(1, "Kommt wieder", state="opened")
    r = client.post("/api/gitlab/sync")
    assert r.json()["wieder_geoeffnet"] == 1
    assert [t["titel"] for t in client.get("/api/tasks").json()] == ["Kommt wieder"]


def test_lokale_aenderung_wird_gepusht(client, fake):
    _verbinden(client)
    fake.issue(1, "Alter Titel", geaendert=_utc_jetzt() - timedelta(hours=2))
    client.post("/api/gitlab/sync")

    task = client.get("/api/tasks").json()[0]
    client.patch(f"/api/tasks/{task['id']}", json={"titel": "Neuer Titel"})
    client.put(f"/api/tasks/{task['id']}/tags/aktiv")

    r = client.post("/api/gitlab/sync")
    assert r.json()["gepusht"] == 1
    titel_update = next(u for u in fake.updates if "title" in u)
    assert titel_update["title"] == "Neuer Titel"
    label_update = next(u for u in fake.updates if "add_labels" in u)
    assert "queue::aktiv" in label_update["add_labels"]
    assert "queue::aktiv" not in label_update["remove_labels"]


def test_remote_aenderung_gewinnt(client, fake):
    _verbinden(client)
    fake.issue(1, "Alter Titel", geaendert=_utc_jetzt() - timedelta(hours=2))
    client.post("/api/gitlab/sync")

    fake.issue(
        1,
        "Titel aus GitLab",
        labels=["queue::next"],
        geaendert=_utc_jetzt() + timedelta(minutes=5),
    )
    r = client.post("/api/gitlab/sync")
    assert r.json()["aktualisiert_lokal"] == 1

    task = client.get("/api/tasks").json()[0]
    assert task["titel"] == "Titel aus GitLab"
    assert task["tags"] == ["next"]
