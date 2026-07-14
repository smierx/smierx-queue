from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Postgres im Produktivbetrieb. Default passt zum docker-compose.
    database_url: str = "postgresql+psycopg://smierx_queue:smierx_queue@localhost:5432/smierx_queue"

    # Keycloak kommt in Phase 4. Bis dahin läuft die API offen (lokales Netz).
    oidc_issuer: str | None = None
    oidc_client_id: str = "smierx-queue"


settings = Settings()
