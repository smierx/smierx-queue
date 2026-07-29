from datetime import datetime, timedelta


def _task(client, titel="Testtask", tags=None):
    r = client.post("/api/tasks", json={"titel": titel, "tags": tags or []})
    assert r.status_code == 201
    return r.json()


def _phasen(client, task_id: int, erledigt=False):
    pfad = "/api/tasks?erledigt=true" if erledigt else f"/api/tasks/{task_id}"
    daten = client.get(pfad).json()
    task = daten if not erledigt else next(t for t in daten if t["id"] == task_id)
    return task["aktiv_phasen"]


def test_aktiv_setzen_oeffnet_phase(client):
    task = _task(client)
    client.put(f"/api/tasks/{task['id']}/tags/aktiv")

    phasen = _phasen(client, task["id"])
    assert len(phasen) == 1
    assert phasen[0]["bis"] is None


def test_anlegen_mit_aktiv_oeffnet_phase(client):
    task = _task(client, tags=["aktiv"])
    assert len(task["aktiv_phasen"]) == 1
    assert task["aktiv_phasen"][0]["bis"] is None


def test_aktiv_entfernen_schliesst_phase(client):
    task = _task(client, tags=["aktiv"])
    client.delete(f"/api/tasks/{task['id']}/tags/aktiv")

    phasen = _phasen(client, task["id"])
    assert len(phasen) == 1
    assert phasen[0]["bis"] is not None


def test_verdraengung_schliesst_phase(client):
    task = _task(client, tags=["aktiv"])
    client.put(f"/api/tasks/{task['id']}/tags/pausiert")

    phasen = _phasen(client, task["id"])
    assert len(phasen) == 1
    assert phasen[0]["bis"] is not None


def test_erledigen_schliesst_phase_und_nimmt_aktiv_runter(client):
    task = _task(client, tags=["aktiv"])
    client.post(f"/api/tasks/{task['id']}/erledigt")

    phasen = _phasen(client, task["id"], erledigt=True)
    assert phasen[0]["bis"] is not None

    # Wiederöffnen startet den Task nicht von selbst.
    r = client.delete(f"/api/tasks/{task['id']}/erledigt")
    assert "aktiv" not in r.json()["tags"]
    assert r.json()["aktiv_seit"] is None


def test_wieder_aktivieren_gibt_neue_phase(client):
    task = _task(client, tags=["aktiv"])
    client.delete(f"/api/tasks/{task['id']}/tags/aktiv")
    client.put(f"/api/tasks/{task['id']}/tags/aktiv")

    phasen = _phasen(client, task["id"])
    assert len(phasen) == 2
    assert phasen[0]["bis"] is not None
    assert phasen[1]["bis"] is None


def test_gesamt_minuten_summiert_phasen(client):
    task = _task(client, "Projekt")
    gestern = (datetime.now() - timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
    for von_h, bis_h in ((9, 10), (14, 15)):
        client.post(
            f"/api/tasks/{task['id']}/phasen",
            json={
                "von": gestern.replace(hour=von_h).isoformat(),
                "bis": gestern.replace(hour=bis_h).isoformat(),
            },
        )

    assert client.get(f"/api/tasks/{task['id']}").json()["gesamt_minuten"] == 120


def test_gesamt_minuten_zaehlt_offene_phase_mit(client):
    task = _task(client, "Läuft", tags=["aktiv"])
    from sqlalchemy import text

    from app.database import engine

    vor_30 = datetime.now() - timedelta(minutes=30)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE task_phases SET von = :z WHERE task_id = :id"),
            {"z": vor_30.isoformat(sep=" "), "id": task["id"]},
        )

    assert 29 <= client.get(f"/api/tasks/{task['id']}").json()["gesamt_minuten"] <= 31


# --- Nachtragen (CRUD) ---


def test_phase_nachtragen_und_im_export(client):
    task = _task(client, "Bürotag")
    gestern = datetime.now() - timedelta(days=1)
    r = client.post(
        f"/api/tasks/{task['id']}/phasen",
        json={
            "von": gestern.replace(hour=9, minute=0).isoformat(),
            "bis": gestern.replace(hour=10, minute=30).isoformat(),
        },
    )
    assert r.status_code == 201

    # Die Timeline des Tages sieht die Phase.
    tag = gestern.date().isoformat()
    phasen = client.get("/api/phasen", params={"datum": tag}).json()
    assert [p["titel"] for p in phasen] == ["Bürotag"]

    # Der Wochen-Export rechnet mit dem nachgetragenen Stand.
    iso = gestern.date().isocalendar()
    export = client.get(
        "/api/export", params={"woche": f"{iso.year}-W{iso.week:02d}"}
    ).json()
    assert any(p["task_id"] == task["id"] and p["minuten"] == 90 for p in export["phasen"])


def test_phase_nachtragen_offen_verboten(client):
    task = _task(client)
    r = client.post(
        f"/api/tasks/{task['id']}/phasen",
        json={"von": datetime.now().isoformat(), "bis": None},
    )
    assert r.status_code == 422


def test_phase_ueberlappung_abgelehnt(client):
    task = _task(client)
    gestern = (datetime.now() - timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
    basis = {"von": gestern.replace(hour=9), "bis": gestern.replace(hour=11)}
    client.post(
        f"/api/tasks/{task['id']}/phasen",
        json={k: v.isoformat() for k, v in basis.items()},
    )

    r = client.post(
        f"/api/tasks/{task['id']}/phasen",
        json={
            "von": gestern.replace(hour=10).isoformat(),
            "bis": gestern.replace(hour=12).isoformat(),
        },
    )
    assert r.status_code == 422

    # Direkt anschließend ist ok.
    r = client.post(
        f"/api/tasks/{task['id']}/phasen",
        json={
            "von": gestern.replace(hour=11).isoformat(),
            "bis": gestern.replace(hour=12).isoformat(),
        },
    )
    assert r.status_code == 201


def test_phase_aendern(client):
    task = _task(client)
    gestern = (datetime.now() - timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
    phase = client.post(
        f"/api/tasks/{task['id']}/phasen",
        json={
            "von": gestern.replace(hour=9).isoformat(),
            "bis": gestern.replace(hour=10).isoformat(),
        },
    ).json()

    r = client.patch(
        f"/api/phasen/{phase['id']}", json={"bis": gestern.replace(hour=11).isoformat()}
    )
    assert r.status_code == 200
    assert r.json()["bis"].startswith(gestern.replace(hour=11).isoformat()[:16])

    r = client.patch(
        f"/api/phasen/{phase['id']}", json={"von": gestern.replace(hour=12).isoformat()}
    )
    assert r.status_code == 422  # von hinter bis


def test_offene_phase_schliessen_beendet_aktiv(client):
    task = _task(client, tags=["aktiv"])
    phase = client.get(f"/api/tasks/{task['id']}").json()["aktiv_phasen"][0]
    phasen_liste = client.get("/api/phasen").json()
    phase_id = next(p["id"] for p in phasen_liste if p["task_id"] == task["id"])
    assert phase["bis"] is None

    r = client.patch(f"/api/phasen/{phase_id}", json={"bis": datetime.now().isoformat()})
    assert r.status_code == 200
    daten = client.get(f"/api/tasks/{task['id']}").json()
    assert "aktiv" not in daten["tags"]
    assert "next" in daten["tags"]


def test_offene_phase_loeschen_beendet_aktiv(client):
    task = _task(client, tags=["aktiv"])
    phase_id = next(
        p["id"] for p in client.get("/api/phasen").json() if p["task_id"] == task["id"]
    )

    r = client.delete(f"/api/phasen/{phase_id}")
    assert r.status_code == 204
    daten = client.get(f"/api/tasks/{task['id']}").json()
    assert daten["aktiv_phasen"] == []
    assert "aktiv" not in daten["tags"]
