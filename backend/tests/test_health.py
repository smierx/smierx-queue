def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_frontend_config_dev_modus(client):
    r = client.get("/api/config")
    assert r.status_code == 200
    daten = r.json()
    assert daten["keycloak_url"] is None
    assert daten["keycloak_realm"] == "smierx"
    assert daten["keycloak_client"] == "smierx-queue"
