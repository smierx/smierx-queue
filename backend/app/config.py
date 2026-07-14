from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Postgres im Produktivbetrieb. Default passt zum docker-compose.
    database_url: str = "postgresql+psycopg://smierx_queue:smierx_queue@localhost:5432/smierx_queue"

    # Keycloak. Ohne oidc_issuer läuft die API im Dev-Modus (ein User "dev", kein Login).
    oidc_issuer: str | None = None
    # Nur nötig wenn die API den Issuer-Host nicht auflösen kann (z.B. im Container).
    oidc_jwks_url: str | None = None


settings = Settings()
