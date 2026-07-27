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
