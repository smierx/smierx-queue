from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app import auth
from app.config import settings

ISSUER = "https://keycloak.test/realms/smierx"

_privat = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_oeffentlich = _privat.public_key()


class FakeJWKS:
    def get_signing_key_from_jwt(self, token):
        return SimpleNamespace(key=_oeffentlich)


@pytest.fixture()
def oidc(monkeypatch):
    monkeypatch.setattr(settings, "oidc_issuer", ISSUER)
    monkeypatch.setattr(auth, "_jwks_client", lambda: FakeJWKS())


def _token(username: str | None, issuer: str = ISSUER) -> str:
    import time

    claims = {"sub": "egal-uuid", "iss": issuer, "exp": int(time.time()) + 300}
    if username is not None:
        claims["preferred_username"] = username
    return jwt.encode(claims, _privat, algorithm="RS256")


def _auth(username: str) -> dict:
    return {"Authorization": f"Bearer {_token(username)}"}


def test_ohne_token_401(client, oidc):
    assert client.get("/api/tasks").status_code == 401


def test_kaputtes_token_401(client, oidc):
    r = client.get("/api/tasks", headers={"Authorization": "Bearer quatsch"})
    assert r.status_code == 401


def test_falscher_issuer_401(client, oidc):
    token = _token("user-a", issuer="https://boese.test/realms/x")
    r = client.get("/api/tasks", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_token_ohne_username_401(client, oidc):
    token = _token(None)
    r = client.get("/api/tasks", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_gueltiges_token_geht_durch(client, oidc):
    r = client.get("/api/tasks", headers=_auth("user-a"))
    assert r.status_code == 200
    assert r.json() == []


def test_user_sehen_nur_ihre_tasks(client, oidc):
    client.post("/api/tasks", json={"titel": "Task von A"}, headers=_auth("user-a"))
    client.post("/api/tasks", json={"titel": "Task von B"}, headers=_auth("user-b"))

    a = client.get("/api/tasks", headers=_auth("user-a")).json()
    b = client.get("/api/tasks", headers=_auth("user-b")).json()
    assert [t["titel"] for t in a] == ["Task von A"]
    assert [t["titel"] for t in b] == ["Task von B"]

    # Fremde Task-Id liefert 404, nicht die fremden Daten.
    fremde_id = b[0]["id"]
    assert client.get(f"/api/tasks/{fremde_id}", headers=_auth("user-a")).status_code == 404


def test_positionen_und_reorder_pro_user(client, oidc):
    a1 = client.post("/api/tasks", json={"titel": "A1"}, headers=_auth("user-a")).json()
    client.post("/api/tasks", json={"titel": "B1"}, headers=_auth("user-b"))
    a2 = client.post("/api/tasks", json={"titel": "A2"}, headers=_auth("user-a")).json()

    # Positionen zählen pro User, nicht global.
    assert (a1["position"], a2["position"]) == (1, 2)

    # Reorder betrifft nur die eigenen Tasks.
    r = client.put(
        "/api/queue/order",
        json={"task_ids": [a2["id"], a1["id"]]},
        headers=_auth("user-a"),
    )
    assert r.status_code == 200

    b = client.get("/api/tasks", headers=_auth("user-b")).json()
    assert [t["titel"] for t in b] == ["B1"]


def test_schedule_und_kapazitaet_pro_user(client, oidc):
    client.put(
        "/api/schedule",
        json={"modus": "stunden", "stunden_pro_tag": 6},
        headers=_auth("user-a"),
    )
    client.post(
        "/api/timeblocks",
        json={"titel": "Meeting von B", "typ": "meeting",
              "start": "2026-07-14T09:00:00", "ende": "2026-07-14T10:00:00"},
        headers=_auth("user-b"),
    )

    a = client.get("/api/capacity", params={"datum": "2026-07-14"}, headers=_auth("user-a")).json()
    b = client.get("/api/capacity", params={"datum": "2026-07-14"}, headers=_auth("user-b")).json()

    # A hat 6h eingestellt und keinen Block, Bs Meeting zählt nicht bei A.
    assert a["arbeitszeit_minuten"] == 360
    assert a["geblockt_minuten"] == 0
    # B hat Default 8h und sein Meeting.
    assert b["arbeitszeit_minuten"] == 480
    assert b["geblockt_minuten"] == 60


def test_dev_modus_ohne_issuer(client):
    # Ohne oidc_issuer läuft alles als User "dev" ohne Token.
    r = client.post("/api/tasks", json={"titel": "Dev-Task"})
    assert r.status_code == 201
