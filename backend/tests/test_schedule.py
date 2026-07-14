FESTE_ZEITEN = {
    "modus": "feste_zeiten",
    "zeiten": {"mo": ["08:00", "16:30"], "di": ["08:00", "16:30"], "mi": ["08:00", "16:30"],
               "do": ["08:00", "16:30"], "fr": ["08:00", "14:00"], "sa": None, "so": None},
}


def test_default_schedule(client):
    r = client.get("/schedule")
    assert r.status_code == 200
    assert r.json()["modus"] == "stunden"
    assert r.json()["stunden_pro_tag"] == 8.0


def test_schedule_feste_zeiten_setzen(client):
    r = client.put("/schedule", json=FESTE_ZEITEN)
    assert r.status_code == 200
    assert r.json()["modus"] == "feste_zeiten"
    assert r.json()["zeiten"]["fr"] == ["08:00", "14:00"]


def test_feste_zeiten_brauchen_zeiten(client):
    r = client.put("/schedule", json={"modus": "feste_zeiten"})
    assert r.status_code == 422

    verdreht = {"modus": "feste_zeiten", "zeiten": {"mo": ["16:00", "08:00"]}}
    r = client.put("/schedule", json=verdreht)
    assert r.status_code == 422


def test_kapazitaet_stunden_modus(client):
    client.put("/schedule", json={"modus": "stunden", "stunden_pro_tag": 8})
    # 2026-07-14 ist ein Dienstag.
    client.post("/timeblocks", json={"titel": "Daily", "typ": "meeting",
                                     "start": "2026-07-14T09:15:00", "ende": "2026-07-14T09:45:00"})
    client.post("/timeblocks", json={"titel": "Review", "typ": "meeting",
                                     "start": "2026-07-14T11:00:00", "ende": "2026-07-14T12:00:00"})

    r = client.get("/capacity", params={"datum": "2026-07-14"})
    daten = r.json()
    assert daten["arbeitszeit_minuten"] == 480
    assert daten["geblockt_minuten"] == 90
    assert daten["frei_minuten"] == 390
    assert len(daten["bloecke"]) == 2


def test_kapazitaet_feste_zeiten_clippt_bloecke(client):
    client.put("/schedule", json=FESTE_ZEITEN)
    # Block ragt über den Feierabend (16:30) hinaus, zählt nur bis dahin.
    client.post("/timeblocks", json={"titel": "Deploy-Fenster", "typ": "blocker",
                                     "start": "2026-07-14T16:00:00", "ende": "2026-07-14T18:00:00"})

    r = client.get("/capacity", params={"datum": "2026-07-14"})
    daten = r.json()
    assert daten["arbeitszeit_minuten"] == 510  # 08:00 bis 16:30
    assert daten["geblockt_minuten"] == 30
    assert daten["frei_minuten"] == 480


def test_kapazitaet_ueberlappende_bloecke_zaehlen_einfach(client):
    client.put("/schedule", json={"modus": "stunden", "stunden_pro_tag": 8})
    client.post("/timeblocks", json={"titel": "A", "typ": "meeting",
                                     "start": "2026-07-14T09:00:00", "ende": "2026-07-14T10:00:00"})
    client.post("/timeblocks", json={"titel": "B", "typ": "meeting",
                                     "start": "2026-07-14T09:30:00", "ende": "2026-07-14T10:30:00"})

    r = client.get("/capacity", params={"datum": "2026-07-14"})
    assert r.json()["geblockt_minuten"] == 90


def test_kapazitaet_freier_tag(client):
    client.put("/schedule", json=FESTE_ZEITEN)
    # 2026-07-18 ist ein Samstag, zeiten: null.
    r = client.get("/capacity", params={"datum": "2026-07-18"})
    assert r.json()["arbeitszeit_minuten"] == 0
    assert r.json()["frei_minuten"] == 0
