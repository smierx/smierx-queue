from datetime import date, timedelta

from sqlalchemy import text

from app.database import engine


def _task(client, titel="Testtask", tags=None, geplant_am=None):
    daten = {"titel": titel, "tags": tags or []}
    if geplant_am is not None:
        daten["geplant_am"] = geplant_am.isoformat()
    r = client.post("/api/tasks", json=daten)
    assert r.status_code == 201
    return r.json()


def _zurueckdatieren(task_id: int, tage: int) -> None:
    """Einen Task per SQL in die Vergangenheit legen (die API erlaubt das bewusst,
    fürs Setup ist SQL direkter). Position bleibt wie angelegt."""
    alt = date.today() - timedelta(days=tage)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE tasks SET geplant_am = :d WHERE id = :id"),
            {"d": alt.isoformat(), "id": task_id},
        )


def _heutige(client) -> list[dict]:
    return client.get("/api/tasks").json()


def test_rollover_schiebt_alte_an_den_kopf(client):
    heute_a = _task(client, "Heute A")
    heute_b = _task(client, "Heute B")
    alt = _task(client, "Von gestern")
    _zurueckdatieren(alt["id"], 1)

    titel = [t["titel"] for t in _heutige(client)]
    assert titel == ["Von gestern", "Heute A", "Heute B"]
    assert all(t["geplant_am"] == date.today().isoformat() for t in _heutige(client))
    assert [t["id"] for t in _heutige(client)][0] == alt["id"]
    assert heute_a["id"] and heute_b["id"]  # nur gegen unused-Warnungen


def test_rollover_erhaelt_relative_reihenfolge(client):
    # Freitag → Montag: mehrere alte Tage, sortiert nach Tag, dann Position.
    vorgestern = _task(client, "Vorgestern")
    gestern_a = _task(client, "Gestern A")
    gestern_b = _task(client, "Gestern B")
    _zurueckdatieren(vorgestern["id"], 2)
    _zurueckdatieren(gestern_a["id"], 1)
    _zurueckdatieren(gestern_b["id"], 1)

    titel = [t["titel"] for t in _heutige(client)]
    assert titel == ["Vorgestern", "Gestern A", "Gestern B"]


def test_rollover_nimmt_geparkte_mit(client):
    alt = _task(client, "Geparkt", tags=["holding"])
    _zurueckdatieren(alt["id"], 3)

    tasks = _heutige(client)
    assert [t["titel"] for t in tasks] == ["Geparkt"]
    assert tasks[0]["tags"] == ["holding"]


def test_rollover_ist_idempotent(client):
    alt = _task(client, "Alt")
    _zurueckdatieren(alt["id"], 1)

    erste = [(t["id"], t["position"]) for t in _heutige(client)]
    zweite = [(t["id"], t["position"]) for t in _heutige(client)]
    assert erste == zweite


def test_rollover_schliesst_vergessene_phase(client):
    # Feierabend vergessen: die Phase endet um Mitternacht, aktiv wird next.
    alt = _task(client, "Lief noch", tags=["aktiv"])
    _zurueckdatieren(alt["id"], 1)
    # Die Phase startete auch gestern (18:00), nicht erst heute.
    gestern_abend = date.today() - timedelta(days=1)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE task_phases SET von = :z WHERE task_id = :id"),
            {"z": f"{gestern_abend.isoformat()} 18:00:00", "id": alt["id"]},
        )

    tasks = _heutige(client)
    assert tasks[0]["tags"] == ["next"]
    phase = tasks[0]["aktiv_phasen"][-1]
    assert phase["bis"] is not None
    assert phase["bis"].startswith(date.today().isoformat() + "T00:00")


def test_rollover_heute_gestartete_phase_wird_nicht_negativ(client):
    # Task läuft seit heute, wird nachträglich auf gestern datiert: die Phase
    # endet an ihrem eigenen Start, nicht um Mitternacht davor.
    alt = _task(client, "Zurückdatiert", tags=["aktiv"])
    client.patch(
        f"/api/tasks/{alt['id']}",
        json={"geplant_am": (date.today() - timedelta(days=1)).isoformat()},
    )

    task = _heutige(client)[0]
    phase = task["aktiv_phasen"][-1]
    assert phase["bis"] is not None
    assert phase["bis"] >= phase["von"]


def test_rollover_laesst_zukunft_und_erledigte_liegen(client):
    morgen = _task(client, "Morgen", geplant_am=date.today() + timedelta(days=1))
    fertig = _task(client, "Fertig")
    client.post(f"/api/tasks/{fertig['id']}/erledigt")
    _zurueckdatieren(fertig["id"], 1)

    assert _heutige(client) == []
    r = client.get("/api/tasks", params={"datum": morgen["geplant_am"]})
    assert [t["titel"] for t in r.json()] == ["Morgen"]
    archiv = client.get("/api/tasks", params={"erledigt": "true"}).json()
    assert [t["titel"] for t in archiv] == ["Fertig"]


def test_tick_aktiviert_keine_zukunfts_tasks(client):
    from tests.test_queue_tick import _abgelaufen

    alt = _task(client, "Alt", tags=["aktiv"])
    _task(client, "Morgen", geplant_am=date.today() + timedelta(days=1))
    heute = _task(client, "Heute")
    _abgelaufen(alt["id"])

    client.post("/api/queue/tick")
    morgen_tasks = client.get(
        "/api/tasks", params={"datum": (date.today() + timedelta(days=1)).isoformat()}
    ).json()
    assert all("aktiv" not in t["tags"] for t in morgen_tasks)
    heute_tags = client.get(f"/api/tasks/{heute['id']}").json()["tags"]
    assert "aktiv" in heute_tags


def test_umsortieren_pro_tag(client):
    a = _task(client, "A")
    b = _task(client, "B")
    morgen = date.today() + timedelta(days=1)
    m1 = _task(client, "M1", geplant_am=morgen)
    m2 = _task(client, "M2", geplant_am=morgen)

    r = client.put(
        "/api/queue/order",
        json={"task_ids": [m2["id"], m1["id"]], "datum": morgen.isoformat()},
    )
    assert r.status_code == 200
    morgen_titel = [
        t["titel"]
        for t in client.get("/api/tasks", params={"datum": morgen.isoformat()}).json()
    ]
    assert morgen_titel == ["M2", "M1"]

    # Heute-Ids in der Morgen-Reihenfolge sind ein Fehler.
    r = client.put(
        "/api/queue/order",
        json={"task_ids": [a["id"], b["id"]], "datum": morgen.isoformat()},
    )
    assert r.status_code == 422


def test_verschieben_auf_anderen_tag(client):
    a = _task(client, "A")
    morgen = (date.today() + timedelta(days=1)).isoformat()

    r = client.patch(f"/api/tasks/{a['id']}", json={"geplant_am": morgen})
    assert r.json()["geplant_am"] == morgen
    assert _heutige(client) == []
    assert [t["id"] for t in client.get("/api/tasks", params={"datum": morgen}).json()] == [
        a["id"]
    ]
