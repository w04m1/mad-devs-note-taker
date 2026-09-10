"""Fail closed unless the connected database is at this image's exact Alembic head."""

from __future__ import annotations

import sys

import psycopg
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.config import get_settings


def expected_heads() -> set[str]:
    return set(ScriptDirectory.from_config(Config("alembic.ini")).get_heads())


def current_heads(database_url: str) -> set[str]:
    psycopg_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(psycopg_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('public.alembic_version')")
        if cursor.fetchone()[0] is None:
            return set()
        cursor.execute("SELECT version_num FROM alembic_version")
        return {row[0] for row in cursor.fetchall()}


def main() -> int:
    expected = expected_heads()
    if len(expected) != 1:
        print(f"schema gate refused image with Alembic heads {sorted(expected)!r}", file=sys.stderr)
        return 1
    try:
        current = current_heads(get_settings().database_sync_url)
    except psycopg.Error as exc:
        print(f"schema gate could not inspect database: {type(exc).__name__}", file=sys.stderr)
        return 1
    if current != expected:
        print(
            f"schema gate rejected database heads {sorted(current)!r}; "
            f"expected {sorted(expected)!r}",
            file=sys.stderr,
        )
        return 1
    print(f"schema gate accepted Alembic head {next(iter(expected))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
