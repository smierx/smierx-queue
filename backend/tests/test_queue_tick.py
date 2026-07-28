from datetime import datetime, timedelta

from sqlalchemy import text

from app.database import engine


def _task(client, titel="Testtask", tags=None, dauer=None):
    daten = {"titel": titel, "tags": tags or []}
    if dauer is not None:
        daten["dauer_minuten"] = dauer
    r = client.post("/api/tasks", json=daten)
    assert r.status_code == 201
    return r.json()


def _abgelaufen(task_id: int, minuten: int = 120) -> None:
    """Den Phasen-Start so weit zurückdatieren, dass die geplante Zeit vorbei ist
    (Phasen-Zeiten sind lokale naive Zeit)."""
    vorbei = datetime.now() - timedelta(minutes=minuten)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE task_phases SET von = :z WHERE task_id = :id"),
            {"z": vorbei.isoformat(sep=" "), "id": task_id},
        )


def _tags(client, task_id: int) -> list[str]:
    return client.get(f"/api/tasks/{task_id}").json()["tags"]


def test_dauer_default_eine_stunde(client):
    task = _task(client)
    assert task["dauer_minuten"] == 60


def test_dauer_aendern(client):
    task = _task(client)
    r = client.patch(f"/api/tasks/{task['id']}", json={"dauer_minuten": 90})
    assert r.json()["dauer_minuten"] == 90

    r = client.patch(f"/api/tasks/{task['id']}", json={"dauer_minuten": 0})
    assert r.status_code == 422


def test_tick_ohne_tasks(client):
    r = client.post("/api/queue/tick")
    assert r.status_code == 200
    assert r.json() == []


def test_tick_startet_nichts_von_selbst(client):
    # Die Dauer ist eine Schätzung, kein Wecker (Entscheid 2026-07-28):
    # auch wenn A längst über der Zeit ist, bleibt B liegen und A aktiv.
    a = _task(client, "A", tags=["aktiv"], dauer=30)
    b = _task(client, "B", tags=["next"])
    c = _task(client, "C")
    _abgelaufen(a["id"])

    client.post("/api/queue/tick")
    client.post("/api/queue/tick")
    assert "aktiv" in _tags(client, a["id"])
    assert _tags(client, b["id"]) == ["next"]
    assert _tags(client, c["id"]) == []
    # Und es entstehen keine neuen Phasen.
    assert len(client.get(f"/api/tasks/{a['id']}").json()["aktiv_phasen"]) == 1


def test_aktiv_phasen(client):
    task = _task(client)
    assert task["aktiv_phasen"] == []

    client.put(f"/api/tasks/{task['id']}/tags/aktiv")
    client.delete(f"/api/tasks/{task['id']}/tags/aktiv")
    client.put(f"/api/tasks/{task['id']}/tags/aktiv")

    phasen = client.get(f"/api/tasks/{task['id']}").json()["aktiv_phasen"]
    assert len(phasen) == 2
    assert phasen[0]["bis"] is not None
    assert phasen[1]["bis"] is None


def test_aktiv_phase_endet_mit_erledigt(client):
    task = _task(client, tags=["aktiv"])
    client.post(f"/api/tasks/{task['id']}/erledigt")

    r = client.get("/api/tasks?erledigt=true")
    phasen = r.json()[0]["aktiv_phasen"]
    assert len(phasen) == 1
    assert phasen[0]["bis"] is not None


def test_zustand_tags_verdraengen_sich(client):
    task = _task(client, tags=["aktiv", "critical"])

    r = client.put(f"/api/tasks/{task['id']}/tags/pausiert")
    assert r.json()["tags"] == ["critical", "pausiert"]

    historie = client.get(f"/api/tasks/{task['id']}/historie").json()
    assert ("aktiv", "entfernt") in [(e["tag"], e["aktion"]) for e in historie]


def test_zwei_zustand_tags_beim_anlegen_abgelehnt(client):
    r = client.post("/api/tasks", json={"titel": "X", "tags": ["aktiv", "next"]})
    assert r.status_code == 422


def test_feierabend(client):
    a = _task(client, "A", tags=["aktiv"])
    b = _task(client, "B", tags=["aktiv", "critical"])
    c = _task(client, "C")

    r = client.post("/api/queue/feierabend")
    assert r.status_code == 200
    assert _tags(client, a["id"]) == ["next"]
    assert _tags(client, b["id"]) == ["critical", "next"]
    assert _tags(client, c["id"]) == []

    # Die aktiv-Phasen sind zu, und es startet nichts von selbst neu.
    phasen = client.get(f"/api/tasks/{a['id']}").json()["aktiv_phasen"]
    assert phasen[-1]["bis"] is not None
    client.post("/api/queue/tick")
    assert all("aktiv" not in _tags(client, t["id"]) for t in (a, b, c))


def test_hintergrund_tick_rollt_den_tag(client):
    # Die Schleife im Backend hält den Rollover am Laufen, auch ohne Browser.
    from datetime import date

    from app.tick import tick_durchlauf

    alt = _task(client, "Von gestern")
    gestern = (date.today() - timedelta(days=1)).isoformat()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE tasks SET geplant_am = :d WHERE id = :id"),
            {"d": gestern, "id": alt["id"]},
        )

    tick_durchlauf()
    r = client.get(f"/api/tasks/{alt['id']}")
    assert r.json()["geplant_am"] == date.today().isoformat()


def test_hintergrund_tick_ohne_daten(client):
    from app.tick import tick_durchlauf

    tick_durchlauf()  # darf nicht knallen
