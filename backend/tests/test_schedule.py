FESTE_ZEITEN = {
    "modus": "feste_zeiten",
    "zeiten": {"mo": ["08:00", "16:30"], "di": ["08:00", "16:30"], "mi": ["08:00", "16:30"],
               "do": ["08:00", "16:30"], "fr": ["08:00", "14:00"], "sa": None, "so": None},
}


def test_schedule_get_or_create_ueberlebt_race(client, monkeypatch):
    """Zwei parallele Erst-Requests: der Verlierer der UNIQUE-Verletzung liest nach."""
    from app.database import SessionLocal
    from app.models import WorkSchedule
    from app.routers.schedule import _schedule_holen

    gewinner = SessionLocal()
    gewinner.add(WorkSchedule(id=1))
    gewinner.commit()
    gewinner.close()

    verlierer = SessionLocal()
    echtes_scalar = verlierer.scalar
    aufrufe = {"n": 0}

    def scalar_mit_race(stmt):
        aufrufe["n"] += 1
        # Erster Blick: Zeile "noch nicht da" (der andere Request war schneller).
        return None if aufrufe["n"] == 1 else echtes_scalar(stmt)

    monkeypatch.setattr(verlierer, "scalar", scalar_mit_race)
    schedule = _schedule_holen(verlierer)
    assert schedule is not None
    verlierer.close()


def test_default_schedule(client):
    r = client.get("/api/schedule")
    assert r.status_code == 200
    assert r.json()["modus"] == "stunden"
    assert r.json()["stunden_pro_tag"] == 8.0


def test_schedule_feste_zeiten_setzen(client):
    r = client.put("/api/schedule", json=FESTE_ZEITEN)
    assert r.status_code == 200
    assert r.json()["modus"] == "feste_zeiten"
    assert r.json()["zeiten"]["fr"] == ["08:00", "14:00"]


def test_feste_zeiten_brauchen_zeiten(client):
    r = client.put("/api/schedule", json={"modus": "feste_zeiten"})
    assert r.status_code == 422

    verdreht = {"modus": "feste_zeiten", "zeiten": {"mo": ["16:00", "08:00"]}}
    r = client.put("/api/schedule", json=verdreht)
    assert r.status_code == 422


def test_kapazitaet_stunden_modus(client):
    client.put("/api/schedule", json={"modus": "stunden", "stunden_pro_tag": 8})
    # 2026-07-14 ist ein Dienstag.
    client.post("/api/timeblocks", json={"titel": "Daily", "typ": "meeting",
                                     "start": "2026-07-14T09:15:00", "ende": "2026-07-14T09:45:00"})
    client.post("/api/timeblocks", json={"titel": "Review", "typ": "meeting",
                                     "start": "2026-07-14T11:00:00", "ende": "2026-07-14T12:00:00"})

    r = client.get("/api/capacity", params={"datum": "2026-07-14"})
    daten = r.json()
    assert daten["arbeitszeit_minuten"] == 480
    assert daten["geblockt_minuten"] == 90
    assert daten["frei_minuten"] == 390
    assert len(daten["bloecke"]) == 2
    # Stunden-Modus hat kein Tagesfenster.
    assert daten["fenster_von"] is None


def test_kapazitaet_liefert_fenster_bei_festen_zeiten(client):
    client.put("/api/schedule", json=FESTE_ZEITEN)
    daten = client.get("/api/capacity", params={"datum": "2026-07-14"}).json()
    assert daten["fenster_von"] == "08:00"
    assert daten["fenster_bis"] == "16:30"


def test_kapazitaet_feste_zeiten_clippt_bloecke(client):
    client.put("/api/schedule", json=FESTE_ZEITEN)
    # Block ragt über den Feierabend (16:30) hinaus, zählt nur bis dahin.
    client.post("/api/timeblocks", json={"titel": "Deploy-Fenster", "typ": "blocker",
                                     "start": "2026-07-14T16:00:00", "ende": "2026-07-14T18:00:00"})

    r = client.get("/api/capacity", params={"datum": "2026-07-14"})
    daten = r.json()
    assert daten["arbeitszeit_minuten"] == 510  # 08:00 bis 16:30
    assert daten["geblockt_minuten"] == 30
    assert daten["frei_minuten"] == 480


def test_kapazitaet_ueberlappende_bloecke_zaehlen_einfach(client):
    client.put("/api/schedule", json={"modus": "stunden", "stunden_pro_tag": 8})
    client.post("/api/timeblocks", json={"titel": "A", "typ": "meeting",
                                     "start": "2026-07-14T09:00:00", "ende": "2026-07-14T10:00:00"})
    client.post("/api/timeblocks", json={"titel": "B", "typ": "meeting",
                                     "start": "2026-07-14T09:30:00", "ende": "2026-07-14T10:30:00"})

    r = client.get("/api/capacity", params={"datum": "2026-07-14"})
    assert r.json()["geblockt_minuten"] == 90


def test_kapazitaet_freier_tag(client):
    client.put("/api/schedule", json=FESTE_ZEITEN)
    # 2026-07-18 ist ein Samstag, zeiten: null.
    r = client.get("/api/capacity", params={"datum": "2026-07-18"})
    assert r.json()["arbeitszeit_minuten"] == 0
    assert r.json()["frei_minuten"] == 0
