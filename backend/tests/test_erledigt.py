def _task(client, titel="Testtask"):
    return client.post("/api/tasks", json={"titel": titel}).json()


def test_erledigen_und_wieder_oeffnen(client):
    task = _task(client, "Fertig machen")

    r = client.post(f"/api/tasks/{task['id']}/erledigt")
    assert r.status_code == 200
    assert r.json()["erledigt_am"] is not None

    # Raus aus der Queue, drin im Archiv.
    assert client.get("/api/tasks").json() == []
    archiv = client.get("/api/tasks", params={"erledigt": "true"}).json()
    assert [t["id"] for t in archiv] == [task["id"]]

    # Wieder öffnen: zurück in die Queue, hinten eingereiht.
    r = client.delete(f"/api/tasks/{task['id']}/erledigt")
    assert r.json()["erledigt_am"] is None
    assert [t["id"] for t in client.get("/api/tasks").json()] == [task["id"]]


def test_erledigen_ist_idempotent(client):
    task = _task(client)
    erste = client.post(f"/api/tasks/{task['id']}/erledigt").json()["erledigt_am"]
    zweite = client.post(f"/api/tasks/{task['id']}/erledigt").json()["erledigt_am"]
    assert erste == zweite


def test_reorder_ignoriert_erledigte(client):
    a = _task(client, "A")
    b = _task(client, "B")
    c = _task(client, "C")
    client.post(f"/api/tasks/{b['id']}/erledigt")

    # Nur die offenen Ids gehören in die Reihenfolge.
    r = client.put("/api/queue/order", json={"task_ids": [c["id"], a["id"]]})
    assert r.status_code == 200
    assert [t["id"] for t in client.get("/api/tasks").json()] == [c["id"], a["id"]]

    # Eine erledigte Id in der Liste ist ein Fehler.
    r = client.put("/api/queue/order", json={"task_ids": [c["id"], a["id"], b["id"]]})
    assert r.status_code == 422


def test_wieder_oeffnen_reiht_hinten_ein(client):
    a = _task(client, "A")
    b = _task(client, "B")
    client.post(f"/api/tasks/{a['id']}/erledigt")
    client.delete(f"/api/tasks/{a['id']}/erledigt")

    assert [t["id"] for t in client.get("/api/tasks").json()] == [b["id"], a["id"]]
