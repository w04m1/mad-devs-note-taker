from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    app_name: str = "Notetaker"
    environment: str = "development"
    database_url: str = "postgresql+asyncpg://notetaker:notetaker@localhost/notetaker"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_from: str = "notetaker@example.test"
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = False
    smtp_timeout_seconds: int = 10
    app_default_email: str = "demo@example.test"
    app_default_timezone: str = "Europe/Budapest"
    reminder_scan_interval_seconds: int = 1
    reminder_grace_seconds: int = 60
    reminder_claim_seconds: int = 30
    outbox_poll_interval_seconds: int = 1
    trash_cleanup_interval_seconds: int = 3600
    max_series_occurrences: int = 10_000
    allowed_origins: str = "http://localhost:5173"
    log_level: str = "INFO"

    @property
    def database_sync_url(self) -> str:
        """Use the same database endpoint through psycopg for Alembic and workers."""
        url = make_url(self.database_url)
        return url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
