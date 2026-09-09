from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    app_name: str = "Notetaker"
    environment: str = "development"
    database_url: str = "postgresql+asyncpg://notetaker:notetaker@localhost/notetaker"
    database_sync_url: str = "postgresql+psycopg://notetaker:notetaker@localhost/notetaker"
    default_email: str = "demo@example.test"
    default_timezone: str = "Europe/Budapest"
    reminder_scan_seconds: int = 1
    reminder_grace_seconds: int = 60
    reminder_claim_seconds: int = 30
    max_series_occurrences: int = 10_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
