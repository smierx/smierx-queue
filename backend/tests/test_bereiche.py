from datetime import date, datetime, timedelta

from sqlalchemy import text

from app.database import engine


def _task(client, titel="Testtask", bereich="arbeit", tags=None, geplant_am=None):
    daten = {"titel": titel, "bereich": bereich, "tags": tags or []}
    if geplant_am is not None:
        daten["geplant_am"] = geplant_am.isoformat()
    r = client.post("/api/tasks", json=daten)
    assert r.status_code == 201
    return r.json()


def _titel(client, bereich, **params):
    r = client.get("/api/tasks", params={"bereich": bereich, **params})
    return [t["titel"] for t in r.json()]


def _tags_je_titel(client, bereich) -> dict[str, list[str]]:
    r = client.get("/api/tasks", params={"bereich": bereich})
    return {t["titel"]: t["tags"] for t in r.json()}


def test_tageslisten_sind_getrennt(client):
    _task(client, "Deployment", "arbeit")
    _task(client, "Einkaufen", "privat")

    assert _titel(client, "arbeit") == ["Deployment"]
    assert _titel(client, "privat") == ["Einkaufen"]


def test_unbekannter_bereich_abgelehnt(client):
    r = client.post("/api/tasks", json={"titel": "X", "bereich": "verein"})
    assert r.status_code == 422
    assert client.get("/api/tasks", params={"bereich": "verein"}).status_code == 422


def test_positionen_pro_bereich(client):
    a = _task(client, "A", "arbeit")
    p = _task(client, "P", "privat")
    # Beide starten bei Position 1, weil die Queues getrennt zählen.
    assert a["position"] == 1
    assert p["position"] == 1


def test_archiv_pro_bereich(client):
    a = _task(client, "Fertig Arbeit", "arbeit")
    p = _task(client, "Fertig Privat", "privat")
    client.post(f"/api/tasks/{a['id']}/erledigt")
    client.post(f"/api/tasks/{p['id']}/erledigt")

    assert _titel(client, "arbeit", erledigt="true") == ["Fertig Arbeit"]
    assert _titel(client, "privat", erledigt="true") == ["Fertig Privat"]


def test_bereichswechsel_ans_ziel_ende(client):
    _task(client, "P1", "privat")
    a = _task(client, "Wechsler", "arbeit")

    r = client.patch(f"/api/tasks/{a['id']}", json={"bereich": "privat"})
    assert r.json()["bereich"] == "privat"
    assert r.json()["position"] == 2  # hinter P1
    assert _titel(client, "arbeit") == []
    assert _titel(client, "privat") == ["P1", "Wechsler"]


def test_bereichswechsel_aktiver_task_laeuft_weiter(client):
    a = _task(client, "Läuft", "arbeit", tags=["aktiv"])

    r = client.patch(f"/api/tasks/{a['id']}", json={"bereich": "privat"})
    daten = r.json()
    assert "aktiv" in daten["tags"]
    assert daten["aktiv_phasen"][-1]["bis"] is None  # Phase blieb offen und wandert mit


def test_bereichswechsel_mit_tageswechsel(client):
    morgen = date.today() + timedelta(days=1)
    _task(client, "P-Morgen", "privat", geplant_am=morgen)
    a = _task(client, "Beides", "arbeit")

    r = client.patch(
        f"/api/tasks/{a['id']}",
        json={"bereich": "privat", "geplant_am": morgen.isoformat()},
    )
    assert (r.json()["bereich"], r.json()["geplant_am"]) == ("privat", morgen.isoformat())
    assert _titel(client, "privat", datum=morgen.isoformat()) == ["P-Morgen", "Beides"]


def test_order_pro_bereich(client):
    a1 = _task(client, "A1", "arbeit")
    a2 = _task(client, "A2", "arbeit")
    p = _task(client, "P", "privat")

    r = client.put(
        "/api/queue/order",
        json={"task_ids": [a2["id"], a1["id"]], "bereich": "arbeit"},
    )
    assert r.status_code == 200
    assert _titel(client, "arbeit") == ["A2", "A1"]

    # Eine fremde Bereichs-Id in der Reihenfolge ist ein Fehler.
    r = client.put(
        "/api/queue/order",
        json={"task_ids": [a2["id"], a1["id"], p["id"]], "bereich": "arbeit"},
    )
    assert r.status_code == 422


def test_rollover_rollt_pro_bereich(client):
    alt_a = _task(client, "Alt Arbeit", "arbeit")
    alt_p = _task(client, "Alt Privat", "privat")
    _task(client, "Heute Arbeit", "arbeit")
    gestern = (date.today() - timedelta(days=1)).isoformat()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE tasks SET geplant_am = :d WHERE id IN (:a, :p)"),
            {"d": gestern, "a": alt_a["id"], "p": alt_p["id"]},
        )

    assert _titel(client, "arbeit") == ["Alt Arbeit", "Heute Arbeit"]
    assert _titel(client, "privat") == ["Alt Privat"]
    # Positionen zählen je Bereich wieder ab 1.
    arbeit = client.get("/api/tasks", params={"bereich": "arbeit"}).json()
    privat = client.get("/api/tasks", params={"bereich": "privat"}).json()
    assert [t["position"] for t in arbeit] == [1, 2]
    assert [t["position"] for t in privat] == [1]


def _abgelaufen(task_id: int, minuten: int = 120) -> None:
    vorbei = datetime.now() - timedelta(minutes=minuten)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE task_phases SET von = :z WHERE task_id = :id"),
            {"z": vorbei.isoformat(sep=" "), "id": task_id},
        )


def test_uebergabe_pro_bereich_unabhaengig(client):
    # Arbeits-Task läuft noch in seiner Zeit, privat ist einer abgelaufen:
    # nur der private Nachfolger wird aktiv.
    _task(client, "Arbeit läuft", "arbeit", tags=["aktiv"])
    alt_p = _task(client, "Privat alt", "privat", tags=["aktiv"])
    _task(client, "Privat next", "privat")
    _task(client, "Arbeit wartet", "arbeit")
    _abgelaufen(alt_p["id"])

    client.post("/api/queue/tick", params={"bereich": "arbeit"})
    assert "aktiv" not in _tags_je_titel(client, "arbeit")["Arbeit wartet"]
    # Der Tick bedient beide Bereiche, egal welcher ihn angestoßen hat.
    assert "aktiv" in _tags_je_titel(client, "privat")["Privat next"]


def test_privater_blocker_pausiert_arbeit_nicht(client):
    alt = _task(client, "Arbeit alt", "arbeit", tags=["aktiv"])
    _task(client, "Arbeit next", "arbeit")
    _abgelaufen(alt["id"])
    jetzt = datetime.now()
    client.post(
        "/api/timeblocks",
        json={
            "titel": "Privater Termin", "typ": "blocker", "bereich": "privat",
            "start": (jetzt - timedelta(minutes=10)).isoformat(),
            "ende": (jetzt + timedelta(minutes=30)).isoformat(),
        },
    )

    client.post("/api/queue/tick", params={"bereich": "arbeit"})
    # Der fremde Blocker bremst nicht.
    assert "aktiv" in _tags_je_titel(client, "arbeit")["Arbeit next"]


def test_feierabend_nur_im_bereich(client):
    a = _task(client, "Arbeit aktiv", "arbeit", tags=["aktiv"])
    p = _task(client, "Privat aktiv", "privat", tags=["aktiv"])

    client.post("/api/queue/feierabend", params={"bereich": "arbeit"})
    assert client.get(f"/api/tasks/{a['id']}").json()["tags"] == ["next"]
    assert "aktiv" in client.get(f"/api/tasks/{p['id']}").json()["tags"]


def test_kapazitaet_und_bloecke_pro_bereich(client):
    client.put(
        "/api/schedule",
        params={"bereich": "privat"},
        json={"modus": "stunden", "stunden_pro_tag": 4},
    )
    jetzt = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
    client.post(
        "/api/timeblocks",
        json={
            "titel": "Meeting", "typ": "meeting", "bereich": "arbeit",
            "start": jetzt.isoformat(),
            "ende": (jetzt + timedelta(hours=1)).isoformat(),
        },
    )

    arbeit = client.get("/api/capacity", params={"bereich": "arbeit"}).json()
    privat = client.get("/api/capacity", params={"bereich": "privat"}).json()
    assert arbeit["arbeitszeit_minuten"] == 480  # Default 8h
    assert arbeit["geblockt_minuten"] == 60
    assert privat["arbeitszeit_minuten"] == 240
    assert privat["geblockt_minuten"] == 0
    assert privat["bloecke"] == []


def test_schedule_lazy_pro_bereich(client):
    arbeit = client.get("/api/schedule", params={"bereich": "arbeit"}).json()
    privat = client.get("/api/schedule", params={"bereich": "privat"}).json()
    assert arbeit["bereich"] == "arbeit"
    assert privat["bereich"] == "privat"


def test_export_pro_bereich(client):
    a = _task(client, "Arbeit fertig", "arbeit")
    p = _task(client, "Privat fertig", "privat")
    client.post(f"/api/tasks/{a['id']}/erledigt")
    client.post(f"/api/tasks/{p['id']}/erledigt")

    arbeit = client.get("/api/export", params={"bereich": "arbeit"}).json()
    privat = client.get("/api/export", params={"bereich": "privat"}).json()
    assert arbeit["bereich"] == "arbeit"
    assert [e["titel"] for e in arbeit["erledigt"]] == ["Arbeit fertig"]
    assert [e["titel"] for e in privat["erledigt"]] == ["Privat fertig"]


def test_phasen_liste_pro_bereich(client):
    _task(client, "Arbeit aktiv", "arbeit", tags=["aktiv"])
    _task(client, "Privat aktiv", "privat", tags=["aktiv"])

    arbeit = client.get("/api/phasen", params={"bereich": "arbeit"}).json()
    privat = client.get("/api/phasen", params={"bereich": "privat"}).json()
    assert [p["titel"] for p in arbeit] == ["Arbeit aktiv"]
    assert [p["titel"] for p in privat] == ["Privat aktiv"]


def test_wieder_oeffnen_bleibt_im_bereich(client):
    p = _task(client, "Privat fertig", "privat")
    client.post(f"/api/tasks/{p['id']}/erledigt")

    r = client.delete(f"/api/tasks/{p['id']}/erledigt")
    assert r.json()["bereich"] == "privat"
    assert _titel(client, "privat") == ["Privat fertig"]
    assert _titel(client, "arbeit") == []
