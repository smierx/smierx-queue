from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Postgres im Produktivbetrieb. Default passt zum docker-compose.
    database_url: str = "postgresql+psycopg://smierx_queue:smierx_queue@localhost:5432/smierx_queue"

    # Hintergrund-Tick für den automatischen Statuswechsel. 0 schaltet ihn ab.
    tick_intervall_sekunden: int = 60

    # Keycloak. Ohne oidc_issuer läuft die API im Dev-Modus (ein User "dev", kein Login).
    oidc_issuer: str | None = None
    # Nur nötig wenn die API den Issuer-Host nicht auflösen kann (z.B. im Container).
    oidc_jwks_url: str | None = None

    # Was das Frontend über /api/config bekommt. Leer = Frontend startet ohne Login.
    frontend_keycloak_url: str | None = None
    frontend_keycloak_realm: str = "smierx"
    frontend_keycloak_client: str = "smierx-queue"


settings = Settings()
