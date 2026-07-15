def _task(client, titel="Testtask", tags=None):
    r = client.post("/api/tasks", json={"titel": titel, "tags": tags or []})
    assert r.status_code == 201
    return r.json()


def test_task_anlegen_und_lesen(client):
    task = _task(client, "Alembic-Migration schreiben", tags=["next"])
    assert task["titel"] == "Alembic-Migration schreiben"
    assert task["tags"] == ["next"]
    assert task["position"] == 1

    r = client.get(f"/api/tasks/{task['id']}")
    assert r.status_code == 200
    assert r.json()["titel"] == "Alembic-Migration schreiben"


def test_positionen_zaehlen_hoch(client):
    a = _task(client, "Erster")
    b = _task(client, "Zweiter")
    assert (a["position"], b["position"]) == (1, 2)


def test_unbekanntes_tag_wird_abgelehnt(client):
    r = client.post("/api/tasks", json={"titel": "X", "tags": ["dringend"]})
    assert r.status_code == 422

    task = _task(client)
    r = client.put(f"/api/tasks/{task['id']}/tags/dringend")
    assert r.status_code == 422


def test_mehrere_tags_gleichzeitig(client):
    task = _task(client, tags=["aktiv", "critical"])
    assert task["tags"] == ["aktiv", "critical"]


def test_tag_setzen_und_entfernen(client):
    task = _task(client)
    r = client.put(f"/api/tasks/{task['id']}/tags/aktiv")
    assert r.json()["tags"] == ["aktiv"]

    # Doppelt setzen ist idempotent.
    r = client.put(f"/api/tasks/{task['id']}/tags/aktiv")
    assert r.json()["tags"] == ["aktiv"]

    r = client.delete(f"/api/tasks/{task['id']}/tags/aktiv")
    assert r.json()["tags"] == []


def test_tag_historie(client):
    task = _task(client, tags=["next"])
    # aktiv verdrängt next (Zustand-Tags schließen sich aus), beides landet in der Historie.
    client.put(f"/api/tasks/{task['id']}/tags/aktiv")
    client.delete(f"/api/tasks/{task['id']}/tags/aktiv")

    r = client.get(f"/api/tasks/{task['id']}/historie")
    eintraege = [(e["tag"], e["aktion"]) for e in r.json()]
    assert eintraege == [
        ("next", "gesetzt"),
        ("next", "entfernt"),
        ("aktiv", "gesetzt"),
        ("aktiv", "entfernt"),
    ]


def test_aktiv_seit(client):
    task = _task(client)
    assert task["aktiv_seit"] is None

    r = client.put(f"/api/tasks/{task['id']}/tags/aktiv")
    assert r.json()["aktiv_seit"] is not None

    r = client.delete(f"/api/tasks/{task['id']}/tags/aktiv")
    assert r.json()["aktiv_seit"] is None

    # Erneut aktiv: aktiv_seit kommt vom neuen gesetzt-Event, nicht vom alten.
    r = client.put(f"/api/tasks/{task['id']}/tags/aktiv")
    assert r.json()["aktiv_seit"] is not None


def test_filter_nach_tag(client):
    _task(client, "Ohne Tag")
    aktiv = _task(client, "Läuft", tags=["aktiv"])

    r = client.get("/api/tasks", params={"tag": "aktiv"})
    assert [t["id"] for t in r.json()] == [aktiv["id"]]

    r = client.get("/api/tasks", params={"tag": "quatsch"})
    assert r.status_code == 422


def test_task_aendern_und_loeschen(client):
    task = _task(client)
    r = client.patch(f"/api/tasks/{task['id']}", json={"beschreibung": "Mehr Kontext"})
    assert r.json()["beschreibung"] == "Mehr Kontext"

    r = client.delete(f"/api/tasks/{task['id']}")
    assert r.status_code == 204
    assert client.get(f"/api/tasks/{task['id']}").status_code == 404


def test_queue_umsortieren(client):
    a, b, c = (_task(client, t)["id"] for t in ("A", "B", "C"))

    r = client.put("/api/queue/order", json={"task_ids": [c, a, b]})
    assert r.status_code == 200
    assert [t["id"] for t in r.json()] == [c, a, b]

    r = client.get("/api/tasks")
    assert [t["id"] for t in r.json()] == [c, a, b]


def test_umsortieren_braucht_alle_ids(client):
    a = _task(client, "A")["id"]
    _task(client, "B")

    r = client.put("/api/queue/order", json={"task_ids": [a]})
    assert r.status_code == 422

    r = client.put("/api/queue/order", json={"task_ids": [a, a]})
    assert r.status_code == 422
