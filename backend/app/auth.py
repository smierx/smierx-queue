from functools import lru_cache

import jwt
from fastapi import HTTPException, Request
from jwt import PyJWKClient

from app.config import settings


@lru_cache(maxsize=1)
def _jwks_client() -> PyJWKClient:
    url = settings.oidc_jwks_url or f"{settings.oidc_issuer}/protocol/openid-connect/certs"
    return PyJWKClient(url)


def aktueller_user(request: Request) -> str:
    """Liefert die User-Id (Keycloak `sub`). Ohne konfiguriertes OIDC: Dev-Modus."""
    if not settings.oidc_issuer:
        return "dev"

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Bearer-Token fehlt")

    token = auth.removeprefix("Bearer ")
    try:
        key = _jwks_client().get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            issuer=settings.oidc_issuer,
            # Keycloak setzt aud standardmäßig auf "account", das prüfen wir nicht.
            options={"verify_aud": False},
        )
    except jwt.PyJWTError as fehler:
        raise HTTPException(401, f"Token ungültig: {fehler}") from None
    return claims["sub"]
