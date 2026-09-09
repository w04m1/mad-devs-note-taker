from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import text

from app.db.session import async_engine
from app.main import app

pytestmark = pytest.mark.skipif(
    "TEST_DATABASE_URL" not in os.environ,
    reason="set TEST_DATABASE_URL to a migrated PostgreSQL database",
)


@pytest.fixture(autouse=True)
async def clean_database() -> None:
    async with async_engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE outbox_events, notifications, reminder_deliveries, reminder_rules, occurrence_exceptions, series_reminder_templates, series_tags, note_tags, notes, recurrence_series, tags, user_settings CASCADE"
            )
        )


@pytest.fixture
async def client():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as value:
        yield value


async def test_settings_validation_and_version_conflict(client: httpx.AsyncClient) -> None:
    current = (await client.get("/api/v1/settings")).json()
    assert current == {"email": "demo@example.test", "timezone": "Europe/Budapest", "version": 1}
    invalid = await client.patch(
        "/api/v1/settings",
        json={"email": "a@b.test", "timezone": "Mars/Olympus", "expected_version": 1},
    )
    assert invalid.status_code == 422
    changed = await client.patch(
        "/api/v1/settings",
        json={"email": "me@example.test", "timezone": "UTC", "expected_version": 1},
    )
    assert changed.json()["version"] == 2
    stale = await client.patch(
        "/api/v1/settings",
        json={"email": "old@example.test", "timezone": "UTC", "expected_version": 1},
    )
    assert stale.status_code == 409
    assert stale.json()["current"]["version"] == 2


async def test_note_associations_reconcile_and_increment_version(client: httpx.AsyncClient) -> None:
    tag = (await client.post("/api/v1/tags", json={"name": "Work", "color": "#AABBCC"})).json()
    starts = datetime.now(UTC) + timedelta(hours=3)
    created = (
        await client.post(
            "/api/v1/notes",
            json={
                "title": "Plan 100%_literal",
                "body": "body",
                "starts_at": starts.isoformat(),
                "active": True,
                "tag_ids": [],
                "reminder_offsets_minutes": [10],
            },
        )
    ).json()
    assert created["version"] == 1
    changed = (
        await client.patch(
            f"/api/v1/notes/{created['id']}",
            json={
                "title": created["title"],
                "body": created["body"],
                "starts_at": created["starts_at"],
                "active": True,
                "tag_ids": [tag["id"]],
                "reminder_offsets_minutes": [10, 60],
                "expected_version": 1,
            },
        )
    ).json()
    assert changed["version"] == 2
    assert [item["name"] for item in changed["tags"]] == ["Work"]
    assert changed["reminder_offsets_minutes"] == [10, 60]
    literal = await client.get("/api/v1/notes", params={"q": "100%_", "tag_id": tag["id"]})
    assert literal.json()["total"] == 1
    too_short = await client.get("/api/v1/notes", params={"q": "  x "})
    assert too_short.status_code == 422
    async with async_engine.connect() as connection:
        states = (
            (
                await connection.execute(
                    text("SELECT state::text FROM reminder_deliveries ORDER BY due_at")
                )
            )
            .scalars()
            .all()
        )
        events = (
            (
                await connection.execute(
                    text("SELECT event_type FROM outbox_events ORDER BY created_at")
                )
            )
            .scalars()
            .all()
        )
    assert states == ["pending", "pending"]
    assert events == ["tag.created", "note.created", "note.updated"]


async def test_soft_delete_restore_and_future_only_reminders(client: httpx.AsyncClient) -> None:
    starts = datetime.now(UTC) + timedelta(minutes=30)
    note = (
        await client.post(
            "/api/v1/notes",
            json={
                "title": "Restore",
                "starts_at": starts.isoformat(),
                "active": True,
                "tag_ids": [],
                "reminder_offsets_minutes": [10, 60],
            },
        )
    ).json()
    deleted = await client.delete(f"/api/v1/notes/{note['id']}", params={"expected_version": 1})
    assert deleted.status_code == 204
    trash = (await client.get("/api/v1/notes", params={"trash": True})).json()
    assert trash["total"] == 1
    restored = await client.post(
        f"/api/v1/notes/{note['id']}/restore", json={"expected_version": 2}
    )
    assert restored.status_code == 200
    assert restored.json()["version"] == 3
    async with async_engine.connect() as connection:
        states = dict(
            (
                await connection.execute(
                    text(
                        "SELECT rr.offset_minutes, rd.state::text FROM reminder_rules rr JOIN reminder_deliveries rd ON rd.reminder_rule_id=rr.id"
                    )
                )
            ).all()
        )
    assert states == {10: "pending", 60: "missed"}


async def test_views_and_calendar_range_guard(client: httpx.AsyncClient) -> None:
    now = datetime.now(UTC)
    for title, delta in [("Past", -1), ("Today", 1), ("Later", 48)]:
        response = await client.post(
            "/api/v1/notes",
            json={
                "title": title,
                "starts_at": (now + timedelta(hours=delta)).isoformat(),
                "active": True,
                "tag_ids": [],
                "reminder_offsets_minutes": [],
            },
        )
        assert response.status_code == 201
    invalid = await client.get(
        "/api/v1/calendar",
        params={
            "starts_from": now.isoformat(),
            "starts_to": (now + timedelta(days=94)).isoformat(),
        },
    )
    assert invalid.status_code == 422
    view = (await client.get("/api/v1/upcoming")).json()
    assert view["past"]["total"] == 1
    assert view["today"]["total"] >= 1
    assert view["server_now"].endswith("Z")


async def test_readding_removed_offset_starts_new_delivery_cycle(client: httpx.AsyncClient) -> None:
    starts = datetime.now(UTC) + timedelta(hours=4)
    base = {
        "title": "Cycles",
        "body": "",
        "starts_at": starts.isoformat(),
        "active": True,
        "tag_ids": [],
        "reminder_offsets_minutes": [10],
    }
    note = (await client.post("/api/v1/notes", json=base)).json()
    removed = (
        await client.patch(
            f"/api/v1/notes/{note['id']}",
            json={
                **base,
                "reminder_offsets_minutes": [],
                "expected_version": 1,
            },
        )
    ).json()
    response = await client.patch(
        f"/api/v1/notes/{note['id']}",
        json={
            **base,
            "expected_version": removed["version"],
        },
    )
    assert response.status_code == 200
    async with async_engine.connect() as connection:
        cycles = (
            await connection.execute(
                text(
                    "SELECT cycle_number, state::text FROM reminder_deliveries ORDER BY cycle_number"
                )
            )
        ).all()
    assert cycles == [(1, "cancelled"), (2, "pending")]
