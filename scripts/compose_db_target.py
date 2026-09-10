#!/usr/bin/env python3
"""Resolve and validate the database target using Docker Compose's own loader."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit


class TargetError(RuntimeError):
    pass


@dataclass(frozen=True)
class Target:
    database: str
    user: str


def _run(*args: str) -> str:
    completed = subprocess.run(args, check=True, capture_output=True, text=True)
    return completed.stdout


def _compose_config() -> dict[str, object]:
    try:
        return json.loads(_run("docker", "compose", "config", "--format", "json"))
    except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        raise TargetError("could not load the Docker Compose configuration") from exc


def resolve_target(config: dict[str, object]) -> Target:
    try:
        services = config["services"]
        postgres_environment = services["postgres"]["environment"]
        backend_environment = services["backend"]["environment"]
        database = str(postgres_environment["POSTGRES_DB"])
        user = str(postgres_environment["POSTGRES_USER"])
        database_url = str(backend_environment["DATABASE_URL"])
    except (KeyError, TypeError) as exc:
        raise TargetError("Compose is missing the PostgreSQL target configuration") from exc

    parsed = urlsplit(database_url)
    application_database = unquote(parsed.path.lstrip("/"))
    application_user = unquote(parsed.username or "")
    if parsed.hostname not in {"postgres", "localhost", "127.0.0.1"}:
        raise TargetError(
            f"DATABASE_URL host {parsed.hostname!r} does not target the Compose PostgreSQL service"
        )
    if (application_database, application_user) != (database, user):
        raise TargetError(
            "database target mismatch: Compose PostgreSQL is "
            f"{user}@{database}, but DATABASE_URL is {application_user}@{application_database}"
        )
    if not database or not user or any(char in database + user for char in "\r\n\t"):
        raise TargetError("database and user must be nonempty single-line values")
    return Target(database=database, user=user)


def validate_running_container(target: Target) -> None:
    try:
        container_id = _run("docker", "compose", "ps", "-q", "postgres").strip()
    except subprocess.CalledProcessError as exc:
        raise TargetError("could not inspect the Compose PostgreSQL service") from exc
    if not container_id:
        raise TargetError("the Compose PostgreSQL service is not running")
    try:
        inspected = json.loads(_run("docker", "inspect", container_id))[0]
        entries = inspected["Config"]["Env"]
        running_environment = dict(entry.split("=", 1) for entry in entries if "=" in entry)
    except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError, IndexError) as exc:
        raise TargetError("could not inspect the running PostgreSQL target") from exc
    running = Target(
        database=running_environment.get("POSTGRES_DB", ""),
        user=running_environment.get("POSTGRES_USER", ""),
    )
    if running != target:
        raise TargetError(
            "running PostgreSQL target mismatch: configured "
            f"{target.user}@{target.database}, running {running.user}@{running.database}"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("field", choices=("database", "user", "validate"))
    parser.add_argument("--require-running", action="store_true")
    args = parser.parse_args()
    try:
        target = resolve_target(_compose_config())
        if args.require_running:
            validate_running_container(target)
    except TargetError as exc:
        print(f"database target validation failed: {exc}", file=sys.stderr)
        return 1
    if args.field == "database":
        print(target.database)
    elif args.field == "user":
        print(target.user)
    else:
        print(f"validated database target {target.user}@{target.database}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
