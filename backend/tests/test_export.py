from datetime import date, datetime, timedelta

from sqlalchemy import text

from app.database import engine


def _task(client, titel="Testtask", tags=None, dauer=None):
    daten = {"titel": titel, "tags": tags or []}
    if dauer is not None:
        daten["dauer_minuten"] = dauer
    r = client.post("/api/tasks", json=daten)
    assert r.status_code == 201
    return r.json()


def _phase_verschieben(task_id: int, minuten: int) -> None:
    """Den Phasen-Start um X Minuten zurückschieben (Phasen sind lokale naive Zeit)."""
    zeitpunkt = datetime.now() - timedelta(minutes=minuten)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE task_phases SET von = :z WHERE task_id = :id"),
            {"z": zeitpunkt.isoformat(sep=" "), "id": task_id},
        )


def _aktuelle_woche() -> str:
    iso = date.today().isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def test_export_leere_woche(client):
    r = client.get("/api/export", params={"woche": "2020-W01"})
    assert r.status_code == 200
    daten = r.json()
    assert daten["woche"] == "2020-W01"
    assert daten["phasen"] == []
    assert daten["erledigt"] == []
    assert daten["bloecke"] == []
    assert daten["zusammenfassung"] == {
        "gearbeitet_minuten": 0,
        "geblockt_minuten": 0,
        "erledigte_tasks": 0,
    }


def test_export_default_ist_aktuelle_woche(client):
    r = client.get("/api/export")
    assert r.json()["woche"] == _aktuelle_woche()


def test_export_ungueltige_woche(client):
    assert client.get("/api/export", params={"woche": "29-2026"}).status_code == 422
    assert client.get("/api/export", params={"woche": "2026-W60"}).status_code == 422


def test_export_phase_abzueglich_blocker(client):
    # Phase lief 60 Minuten, davon 20 in einem Meeting → 40 Minuten gearbeitet.
    task = _task(client, "Deployment", tags=["aktiv"])
    client.delete(f"/api/tasks/{task['id']}/tags/aktiv")
    _phase_verschieben(task["id"], 60)
    jetzt = datetime.now()
    client.post(
        "/api/timeblocks",
        json={
            "titel": "Daily", "typ": "meeting",
            "start": (jetzt - timedelta(minutes=40)).isoformat(),
            "ende": (jetzt - timedelta(minutes=20)).isoformat(),
        },
    )

    daten = client.get("/api/export").json()
    assert len(daten["phasen"]) == 1
    phase = daten["phasen"][0]
    assert phase["titel"] == "Deployment"
    assert phase["offen"] is False
    assert 39 <= phase["minuten"] <= 41
    assert len(daten["bloecke"]) == 1
    assert daten["bloecke"][0]["minuten"] == 20
    assert daten["zusammenfassung"]["gearbeitet_minuten"] == phase["minuten"]


def test_export_offene_phase_bis_jetzt(client):
    task = _task(client, "Läuft noch", tags=["aktiv"])
    _phase_verschieben(task["id"], 30)

    daten = client.get("/api/export").json()
    assert len(daten["phasen"]) == 1
    assert daten["phasen"][0]["offen"] is True
    assert 29 <= daten["phasen"][0]["minuten"] <= 31


def test_export_erledigte_der_woche(client):
    task = _task(client, "Fertig", dauer=45)
    client.post(f"/api/tasks/{task['id']}/erledigt")

    daten = client.get("/api/export").json()
    assert len(daten["erledigt"]) == 1
    assert daten["erledigt"][0]["titel"] == "Fertig"
    assert daten["erledigt"][0]["dauer_minuten"] == 45
    assert daten["zusammenfassung"]["erledigte_tasks"] == 1

    # In einer anderen Woche taucht er nicht auf.
    daten = client.get("/api/export", params={"woche": "2020-W01"}).json()
    assert daten["erledigt"] == []
