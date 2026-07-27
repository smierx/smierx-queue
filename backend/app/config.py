from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Postgres im Produktivbetrieb. Default passt zum docker-compose.
    database_url: str = "postgresql+psycopg://smierx_queue:smierx_queue@localhost:5432/smierx_queue"

    # Hintergrund-Tick für den automatischen Statuswechsel. 0 schaltet ihn ab.
    tick_intervall_sekunden: int = 60


settings = Settings()
