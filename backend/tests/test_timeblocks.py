def _block(client, titel="Daily", typ="meeting",
           start="2026-07-14T09:15:00", ende="2026-07-14T09:30:00"):
    r = client.post("/timeblocks", json={"titel": titel, "typ": typ, "start": start, "ende": ende})
    assert r.status_code == 201
    return r.json()


def test_block_anlegen(client):
    block = _block(client)
    assert block["titel"] == "Daily"
    assert block["typ"] == "meeting"


def test_ungueltiger_typ_und_zeitraum(client):
    r = client.post(
        "/timeblocks",
        json={"titel": "X", "typ": "urlaub",
              "start": "2026-07-14T09:00:00", "ende": "2026-07-14T10:00:00"},
    )
    assert r.status_code == 422

    r = client.post(
        "/timeblocks",
        json={"titel": "X", "typ": "blocker",
              "start": "2026-07-14T10:00:00", "ende": "2026-07-14T09:00:00"},
    )
    assert r.status_code == 422


def test_bereichsfilter_zaehlt_ueberlappung(client):
    _block(client, "Montag", start="2026-07-13T09:00:00", ende="2026-07-13T10:00:00")
    dienstag = _block(client, "Dienstag", start="2026-07-14T09:00:00", ende="2026-07-14T10:00:00")
    _block(client, "Mittwoch", start="2026-07-15T09:00:00", ende="2026-07-15T10:00:00")

    r = client.get("/timeblocks", params={"von": "2026-07-14", "bis": "2026-07-14"})
    assert [b["id"] for b in r.json()] == [dienstag["id"]]


def test_block_aendern_und_loeschen(client):
    block = _block(client)
    r = client.put(
        f"/timeblocks/{block['id']}",
        json={"titel": "Daily verschoben", "typ": "meeting",
              "start": "2026-07-14T10:00:00", "ende": "2026-07-14T10:15:00"},
    )
    assert r.json()["titel"] == "Daily verschoben"

    r = client.delete(f"/timeblocks/{block['id']}")
    assert r.status_code == 204
    assert client.get("/timeblocks").json() == []
