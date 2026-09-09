from app.config import Settings


def test_frozen_environment_names_are_loaded(monkeypatch) -> None:
    monkeypatch.setenv("APP_DEFAULT_EMAIL", "owner@example.test")
    monkeypatch.setenv("APP_DEFAULT_TIMEZONE", "UTC")
    monkeypatch.setenv("REMINDER_SCAN_INTERVAL_SECONDS", "7")
    monkeypatch.setenv("OUTBOX_POLL_INTERVAL_SECONDS", "4")
    monkeypatch.setenv("TRASH_CLEANUP_INTERVAL_SECONDS", "99")

    settings = Settings(_env_file=None)

    assert settings.app_default_email == "owner@example.test"
    assert settings.app_default_timezone == "UTC"
    assert settings.reminder_scan_interval_seconds == 7
    assert settings.outbox_poll_interval_seconds == 4
    assert settings.trash_cleanup_interval_seconds == 99


def test_sync_database_url_keeps_endpoint_and_uses_psycopg(monkeypatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://user:secret@postgres:5432/notetaker?sslmode=disable",
    )

    settings = Settings(_env_file=None)

    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.database_sync_url == (
        "postgresql+psycopg://user:secret@postgres:5432/notetaker?sslmode=disable"
    )
