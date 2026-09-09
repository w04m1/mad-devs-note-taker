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


async def test_series_materialization_and_occurrence_exception_lifecycle(
    client: httpx.AsyncClient,
) -> None:
    first = (datetime.now(UTC) + timedelta(days=10)).replace(microsecond=0)
    payload = {
        "title": "Daily standup",
        "body": "template",
        "starts_at": first.isoformat(),
        "active": True,
        "tag_ids": [],
        "reminder_offsets_minutes": [10],
        "local_start": first.replace(tzinfo=None).isoformat(),
        "timezone": "UTC",
        "frequency": "daily",
        "end_date": (first.date() + timedelta(days=2)).isoformat(),
    }
    created_response = await client.post("/api/v1/series", json=payload)
    assert created_response.status_code == 201, created_response.text
    series = created_response.json()
    assert series["occurrence_count"] == 3
    listed = (await client.get("/api/v1/notes")).json()["items"]
    occurrences = [item for item in listed if item["series_id"] == series["id"]]
    assert len(occurrences) == 3
    assert [x["starts_at"] for x in occurrences] == [
        (first + timedelta(days=n)).isoformat().replace("+00:00", "Z") for n in range(3)
    ]
    selected = occurrences[1]
    moved = first + timedelta(days=1, hours=2)
    changed_response = await client.patch(
        f"/api/v1/notes/{selected['id']}",
        json={
            "title": "Moved",
            "body": "override",
            "starts_at": moved.isoformat(),
            "active": True,
            "tag_ids": [],
            "reminder_offsets_minutes": [10],
            "expected_version": selected["version"],
            "expected_series_version": series["version"],
        },
    )
    assert changed_response.status_code == 200, changed_response.text
    changed = changed_response.json()
    assert changed["id"] == selected["id"]
    assert changed["recurrence_key"] == selected["recurrence_key"]
    deleted = await client.delete(
        f"/api/v1/notes/{selected['id']}",
        params={"expected_version": changed["version"], "expected_series_version": 2},
    )
    assert deleted.status_code == 204, deleted.text
    restored = await client.post(
        f"/api/v1/notes/{selected['id']}/restore",
        json={"expected_version": changed["version"] + 1, "expected_series_version": 3},
    )
    assert restored.status_code == 200, restored.text
    async with async_engine.connect() as connection:
        exception = (
            await connection.execute(
                text(
                    "SELECT cancelled, overridden_fields FROM occurrence_exceptions WHERE series_id=:id"
                ),
                {"id": series["id"]},
            )
        ).one()
    assert exception.cancelled is False
    assert exception.overridden_fields["title"] == "Moved"
    assert exception.overridden_fields["starts_at"].startswith(moved.isoformat())


async def test_series_limit_validation_is_atomic(client: httpx.AsyncClient) -> None:
    first = (datetime.now(UTC) + timedelta(days=30)).replace(microsecond=0)
    response = await client.post(
        "/api/v1/series",
        json={
            "title": "Too many",
            "body": "",
            "starts_at": first.isoformat(),
            "active": True,
            "tag_ids": [],
            "reminder_offsets_minutes": [],
            "local_start": first.replace(tzinfo=None).isoformat(),
            "timezone": "UTC",
            "frequency": "daily",
            "end_date": (first.date() + timedelta(days=10_000)).isoformat(),
        },
    )
    assert response.status_code == 422
    async with async_engine.connect() as connection:
        assert (
            await connection.execute(text("SELECT count(*) FROM recurrence_series"))
        ).scalar_one() == 0
        assert (await connection.execute(text("SELECT count(*) FROM notes"))).scalar_one() == 0


async def test_series_split_replaces_future_exceptions_and_portion_trash_restores(
    client: httpx.AsyncClient,
) -> None:
    first = (datetime.now(UTC) + timedelta(days=40)).replace(microsecond=0)
    create_payload = {
        "title": "Original",
        "body": "",
        "starts_at": first.isoformat(),
        "active": True,
        "tag_ids": [],
        "reminder_offsets_minutes": [10],
        "local_start": first.replace(tzinfo=None).isoformat(),
        "timezone": "UTC",
        "frequency": "daily",
        "end_date": (first.date() + timedelta(days=3)).isoformat(),
    }
    series = (await client.post("/api/v1/series", json=create_payload)).json()
    occurrences = [
        item
        for item in (await client.get("/api/v1/notes", params={"page_size": 100})).json()["items"]
        if item["series_id"] == series["id"]
    ]
    occurrences.sort(key=lambda item: item["recurrence_key"])

    overridden = occurrences[2]
    changed = await client.patch(
        f"/api/v1/notes/{overridden['id']}",
        json={
            "title": "Discard this override",
            "body": "",
            "starts_at": overridden["starts_at"],
            "active": True,
            "tag_ids": [],
            "reminder_offsets_minutes": [10],
            "expected_version": overridden["version"],
            "expected_series_version": series["version"],
        },
    )
    assert changed.status_code == 200, changed.text

    selected = occurrences[1]
    split_payload = {
        **create_payload,
        "title": "Replacement",
        "starts_at": selected["recurrence_key"],
        "local_start": (first + timedelta(days=1)).replace(tzinfo=None).isoformat(),
        "recurrence_key": selected["recurrence_key"],
        "expected_version": series["version"] + 1,
        "expected_occurrence_version": selected["version"],
    }
    split = await client.post(f"/api/v1/series/{series['id']}/split", json=split_payload)
    assert split.status_code == 200, split.text
    successor = split.json()
    assert successor["predecessor_id"] == series["id"]
    assert successor["lineage_id"] == series["lineage_id"]
    assert successor["occurrence_count"] == 3

    visible = (await client.get("/api/v1/notes", params={"page_size": 100})).json()["items"]
    lineage_notes = [
        item for item in visible if item["series_id"] in {series["id"], successor["id"]}
    ]
    assert len(lineage_notes) == 4
    replacement = [item for item in lineage_notes if item["series_id"] == successor["id"]]
    assert {item["id"] for item in replacement} == {item["id"] for item in occurrences[1:]}
    assert {item["title"] for item in replacement} == {"Replacement"}

    boundary = replacement[1]["recurrence_key"]
    trashed = await client.post(
        f"/api/v1/series/{successor['id']}/trash",
        json={"expected_version": successor["version"], "recurrence_key": boundary},
    )
    assert trashed.status_code == 204, trashed.text
    trash = (await client.get("/api/v1/notes", params={"trash": True, "page_size": 100})).json()[
        "items"
    ]
    assert len([item for item in trash if item["series_id"] == successor["id"]]) == 2

    restored = await client.post(
        f"/api/v1/series/{successor['id']}/restore",
        json={"expected_version": successor["version"] + 1, "recurrence_key": boundary},
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["version"] == successor["version"] + 2
