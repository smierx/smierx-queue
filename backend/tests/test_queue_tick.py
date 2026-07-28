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


def test_tick_ohne_aktive_bleibt_still(client):
    # Kein Task aktiv (z.B. nach Feierabend) → der Tick startet nichts von selbst.
    a = _task(client, "A")
    b = _task(client, "B", tags=["next"])

    r = client.post("/api/queue/tick")
    assert r.status_code == 200
    assert _tags(client, a["id"]) == []
    assert _tags(client, b["id"]) == ["next"]


def test_tick_bevorzugt_next(client):
    alt = _task(client, "Alt", tags=["aktiv"])
    _task(client, "A")
    b = _task(client, "B", tags=["next"])
    _abgelaufen(alt["id"])

    client.post("/api/queue/tick")
    assert "aktiv" in _tags(client, b["id"])


def test_tick_ueberspringt_geparkte(client):
    alt = _task(client, "Alt", tags=["aktiv"])
    a = _task(client, "A", tags=["pausiert"])
    b = _task(client, "B", tags=["holding"])
    c = _task(client, "C")
    _abgelaufen(alt["id"])

    client.post("/api/queue/tick")
    assert "aktiv" not in _tags(client, a["id"])
    assert "aktiv" not in _tags(client, b["id"])
    assert "aktiv" in _tags(client, c["id"])


def test_tick_nimmt_next_beim_aktivieren_runter(client):
    alt = _task(client, "Alt", tags=["aktiv"])
    b = _task(client, "B", tags=["next"])
    _abgelaufen(alt["id"])

    client.post("/api/queue/tick")
    assert _tags(client, b["id"]) == ["aktiv"]


def test_tick_laesst_laufende_in_ruhe(client):
    _task(client, "A", tags=["aktiv"])
    b = _task(client, "B")

    client.post("/api/queue/tick")
    assert _tags(client, b["id"]) == []


def test_tick_aktiviert_naechsten_nach_ablauf(client):
    a = _task(client, "A", tags=["aktiv"])
    b = _task(client, "B")
    _abgelaufen(a["id"])

    client.post("/api/queue/tick")
    # A bleibt aktiv (wird nie automatisch beendet), B kommt dazu.
    assert "aktiv" in _tags(client, a["id"])
    assert "aktiv" in _tags(client, b["id"])


def _blocker(client, von: datetime, bis: datetime, titel="Meeting"):
    r = client.post(
        "/api/timeblocks",
        json={"titel": titel, "typ": "meeting", "start": von.isoformat(), "ende": bis.isoformat()},
    )
    assert r.status_code == 201


def test_tick_wartet_im_blocker(client):
    alt = _task(client, "Alt", tags=["aktiv"])
    b = _task(client, "B")
    _abgelaufen(alt["id"])
    jetzt = datetime.now()
    _blocker(client, jetzt - timedelta(minutes=10), jetzt + timedelta(minutes=30))

    client.post("/api/queue/tick")
    assert _tags(client, b["id"]) == []


def test_tick_blocker_schiebt_geplantes_ende(client):
    # A läuft seit 50 Minuten mit Dauer 30, aber 40 Minuten davon waren geblockt.
    # Geplantes Ende liegt also noch in der Zukunft, B darf nicht aktiviert werden.
    a = _task(client, "A", tags=["aktiv"], dauer=30)
    b = _task(client, "B")
    _abgelaufen(a["id"], minuten=50)
    jetzt = datetime.now()
    _blocker(client, jetzt - timedelta(minutes=40), jetzt - timedelta(minutes=1))

    client.post("/api/queue/tick")
    assert _tags(client, b["id"]) == []


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

    # Die aktiv-Phasen sind zu, und der Tick bleibt danach still.
    phasen = client.get(f"/api/tasks/{a['id']}").json()["aktiv_phasen"]
    assert phasen[-1]["bis"] is not None
    client.post("/api/queue/tick")
    assert all("aktiv" not in _tags(client, t["id"]) for t in (a, b, c))


def test_tick_reaktiviert_degradierten_task_nicht(client):
    # A ist über der Zeit, der Tick startet B. Nimmt Michel B das aktiv wieder
    # weg, bleibt die Übergabe still, statt B alle 30s neu zu starten.
    a = _task(client, "A", tags=["aktiv"])
    b = _task(client, "B")
    _abgelaufen(a["id"])

    client.post("/api/queue/tick")
    assert "aktiv" in _tags(client, b["id"])
    client.delete(f"/api/tasks/{b['id']}/tags/aktiv")

    client.post("/api/queue/tick")
    client.post("/api/queue/tick")
    assert "aktiv" not in _tags(client, b["id"])
    # Und es entstehen keine weiteren Phasen-Duplikate.
    assert len(client.get(f"/api/tasks/{b['id']}").json()["aktiv_phasen"]) == 1


def test_tick_rueckt_nach_erledigen_normal_weiter(client):
    # Kette bleibt intakt: B wurde auto-gestartet und fertig gemacht,
    # A liegt weiter überzogen daneben → C rückt nach.
    a = _task(client, "A", tags=["aktiv"])
    b = _task(client, "B")
    c = _task(client, "C")
    _abgelaufen(a["id"])

    client.post("/api/queue/tick")
    assert "aktiv" in _tags(client, b["id"])
    client.post(f"/api/tasks/{b['id']}/erledigt")

    client.post("/api/queue/tick")
    assert "aktiv" in _tags(client, c["id"])
    assert "aktiv" in _tags(client, a["id"])  # A wird weiterhin nie automatisch beendet


def test_tick_hoechstens_ein_wechsel(client):
    a = _task(client, "A", tags=["aktiv"])
    b = _task(client, "B")
    c = _task(client, "C")
    _abgelaufen(a["id"])

    client.post("/api/queue/tick")
    assert "aktiv" in _tags(client, b["id"])
    assert "aktiv" not in _tags(client, c["id"])


def test_hintergrund_tick_wechselt_ohne_request(client):
    # Die Schleife im Backend macht die Übergabe auch ohne offenen Browser.
    from app.tick import tick_durchlauf

    a = _task(client, "A", tags=["aktiv"])
    b = _task(client, "B")
    _abgelaufen(a["id"])

    tick_durchlauf()
    assert "aktiv" in _tags(client, b["id"])


def test_hintergrund_tick_ohne_daten(client):
    from app.tick import tick_durchlauf

    tick_durchlauf()  # darf nicht knallen
