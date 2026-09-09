from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import text

from app.config import Settings, get_settings
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


def _series_payload(
    first: datetime, *, title: str = "Contract series", tag_ids=None, reminders=None
):
    return {
        "title": title,
        "body": "",
        "starts_at": first.isoformat(),
        "active": True,
        "tag_ids": tag_ids or [],
        "reminder_offsets_minutes": reminders or [],
        "local_start": first.replace(tzinfo=None).isoformat(),
        "timezone": "UTC",
        "frequency": "daily",
        "end_date": (first.date() + timedelta(days=2)).isoformat(),
    }


async def test_configured_series_limit_applies_to_create_and_split(
    client: httpx.AsyncClient,
) -> None:
    first = (datetime.now(UTC) + timedelta(days=70)).replace(microsecond=0)
    created = (await client.post("/api/v1/series", json=_series_payload(first))).json()
    notes = (await client.get("/api/v1/notes", params={"page_size": 100})).json()["items"]
    selected = sorted(
        (n for n in notes if n["series_id"] == created["id"]), key=lambda n: n["recurrence_key"]
    )[1]
    app.dependency_overrides[get_settings] = lambda: Settings(
        max_series_occurrences=2, _env_file=None
    )
    try:
        rejected_create = await client.post(
            "/api/v1/series", json=_series_payload(first + timedelta(days=10))
        )
        assert rejected_create.status_code == 422
        split_payload = {
            **_series_payload(first + timedelta(days=1), title="Limited replacement"),
            "recurrence_key": selected["recurrence_key"],
            "expected_version": created["version"],
            "expected_occurrence_version": selected["version"],
        }
        rejected_split = await client.post(
            f"/api/v1/series/{created['id']}/split", json=split_payload
        )
        assert rejected_split.status_code == 422
        assert "exceeds 2" in rejected_split.text
    finally:
        app.dependency_overrides.pop(get_settings, None)
    unchanged = (await client.get(f"/api/v1/series/{created['id']}")).json()
    assert unchanged["version"] == created["version"]
    assert unchanged["occurrence_count"] == 3


async def test_split_replaces_future_series_trash_and_keeps_unchanged_cycles(
    client: httpx.AsyncClient,
) -> None:
    first = (datetime.now(UTC) + timedelta(days=80)).replace(microsecond=0)
    series = (
        await client.post("/api/v1/series", json=_series_payload(first, reminders=[10]))
    ).json()
    notes = (await client.get("/api/v1/notes", params={"page_size": 100})).json()["items"]
    notes = sorted(
        (n for n in notes if n["series_id"] == series["id"]), key=lambda n: n["recurrence_key"]
    )
    trashed = await client.post(
        f"/api/v1/series/{series['id']}/trash",
        json={"expected_version": series["version"], "recurrence_key": notes[1]["recurrence_key"]},
    )
    assert trashed.status_code == 204
    split_payload = {
        **_series_payload(first + timedelta(days=1), title="Replacement"),
        "reminder_offsets_minutes": [10],
        "recurrence_key": notes[1]["recurrence_key"],
        "expected_version": series["version"] + 1,
        "expected_occurrence_version": notes[1]["version"] + 1,
    }
    split = await client.post(f"/api/v1/series/{series['id']}/split", json=split_payload)
    assert split.status_code == 200, split.text
    successor = split.json()
    visible = (await client.get("/api/v1/notes", params={"page_size": 100})).json()["items"]
    replacement = [n for n in visible if n["series_id"] == successor["id"]]
    replacement_ids = {n["id"] for n in replacement}
    assert {notes[1]["id"], notes[2]["id"]} <= replacement_ids
    assert len(replacement_ids) == 3
    async with async_engine.connect() as connection:
        cycles = (
            await connection.execute(
                text("""
            SELECT n.id::text, rr.current_cycle_number, rd.state::text
            FROM notes n JOIN reminder_rules rr ON rr.note_id=n.id
            JOIN reminder_deliveries rd ON rd.reminder_rule_id=rr.id
              AND rd.cycle_number=rr.current_cycle_number
            WHERE n.series_id=:series_id ORDER BY n.recurrence_key
        """),
                {"series_id": successor["id"]},
            )
        ).all()
    assert [(cycle, state) for _, cycle, state in cycles] == [(1, "pending")] * 3


async def test_series_restore_does_not_revive_overlapping_individual_cancellation(
    client: httpx.AsyncClient,
) -> None:
    first = (datetime.now(UTC) + timedelta(days=90)).replace(microsecond=0)
    series = (await client.post("/api/v1/series", json=_series_payload(first))).json()
    notes = (await client.get("/api/v1/notes", params={"page_size": 100})).json()["items"]
    notes = sorted(
        (n for n in notes if n["series_id"] == series["id"]), key=lambda n: n["recurrence_key"]
    )
    assert (
        await client.delete(
            f"/api/v1/notes/{notes[1]['id']}",
            params={
                "expected_version": notes[1]["version"],
                "expected_series_version": series["version"],
            },
        )
    ).status_code == 204
    assert (
        await client.post(
            f"/api/v1/series/{series['id']}/trash",
            json={
                "expected_version": series["version"] + 1,
                "recurrence_key": notes[0]["recurrence_key"],
            },
        )
    ).status_code == 204
    restored = await client.post(
        f"/api/v1/series/{series['id']}/restore",
        json={
            "expected_version": series["version"] + 2,
            "recurrence_key": notes[0]["recurrence_key"],
        },
    )
    assert restored.status_code == 200, restored.text
    trash_ids = {
        n["id"] for n in (await client.get("/api/v1/notes", params={"trash": True})).json()["items"]
    }
    assert trash_ids == {notes[1]["id"]}
    invalid_boundary = await client.post(
        f"/api/v1/series/{series['id']}/restore",
        json={
            "expected_version": series["version"] + 3,
            "recurrence_key": notes[1]["recurrence_key"],
        },
    )
    assert invalid_boundary.status_code == 404


async def test_split_rejects_historical_effective_override(client: httpx.AsyncClient) -> None:
    first = (datetime.now(UTC) + timedelta(days=100)).replace(microsecond=0)
    series = (await client.post("/api/v1/series", json=_series_payload(first))).json()
    notes = (await client.get("/api/v1/notes", params={"page_size": 100})).json()["items"]
    notes = sorted(
        (n for n in notes if n["series_id"] == series["id"]), key=lambda n: n["recurrence_key"]
    )
    moved_payload = {
        "title": notes[1]["title"],
        "body": "",
        "starts_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
        "active": True,
        "tag_ids": [],
        "reminder_offsets_minutes": [],
        "expected_version": notes[1]["version"],
        "expected_series_version": series["version"],
    }
    assert (
        await client.patch(f"/api/v1/notes/{notes[1]['id']}", json=moved_payload)
    ).status_code == 200
    split_payload = {
        **_series_payload(first, title="Unsafe"),
        "recurrence_key": notes[0]["recurrence_key"],
        "expected_version": series["version"] + 1,
        "expected_occurrence_version": notes[0]["version"],
    }
    rejected = await client.post(f"/api/v1/series/{series['id']}/split", json=split_payload)
    assert rejected.status_code == 409
    assert rejected.json()["code"] == "historical_replacement"


async def test_changed_split_supersedes_old_slots_and_cancels_their_reminders(
    client: httpx.AsyncClient,
) -> None:
    first = (datetime.now(UTC) + timedelta(days=110)).replace(microsecond=0)
    series = (
        await client.post("/api/v1/series", json=_series_payload(first, reminders=[10]))
    ).json()
    notes = (await client.get("/api/v1/notes", params={"page_size": 100})).json()["items"]
    notes = sorted(
        (n for n in notes if n["series_id"] == series["id"]), key=lambda n: n["recurrence_key"]
    )
    shifted = first + timedelta(days=1, hours=2)
    payload = {
        **_series_payload(shifted, title="Shifted"),
        "reminder_offsets_minutes": [10],
        "recurrence_key": notes[1]["recurrence_key"],
        "expected_version": series["version"],
        "expected_occurrence_version": notes[1]["version"],
    }
    split = await client.post(f"/api/v1/series/{series['id']}/split", json=payload)
    assert split.status_code == 200, split.text
    successor = split.json()
    visible_ids = {
        n["id"]
        for n in (await client.get("/api/v1/notes", params={"page_size": 100})).json()["items"]
    }
    assert notes[1]["id"] not in visible_ids and notes[2]["id"] not in visible_ids
    async with async_engine.connect() as connection:
        old = (
            await connection.execute(
                text("""
          SELECT n.superseded_at IS NOT NULL, rd.state::text FROM notes n
          JOIN reminder_rules rr ON rr.note_id=n.id JOIN reminder_deliveries rd ON rd.reminder_rule_id=rr.id
          WHERE n.id IN (:one,:two) ORDER BY n.recurrence_key
        """),
                {"one": notes[1]["id"], "two": notes[2]["id"]},
            )
        ).all()
        fresh_count = (
            await connection.execute(
                text("SELECT count(*) FROM notes WHERE series_id=:id AND superseded_at IS NULL"),
                {"id": successor["id"]},
            )
        ).scalar_one()
    assert old == [(True, "cancelled"), (True, "cancelled")]
    assert fresh_count == 3


async def test_tag_deletion_versions_series_and_occurrences(client: httpx.AsyncClient) -> None:
    tag = (
        await client.post("/api/v1/tags", json={"name": "Series tag", "color": "#123456"})
    ).json()
    first = (datetime.now(UTC) + timedelta(days=120)).replace(microsecond=0)
    series = (
        await client.post("/api/v1/series", json=_series_payload(first, tag_ids=[tag["id"]]))
    ).json()
    assert (
        await client.delete(
            f"/api/v1/tags/{tag['id']}", params={"expected_version": tag["version"]}
        )
    ).status_code == 204
    changed_series = (await client.get(f"/api/v1/series/{series['id']}")).json()
    changed_notes = [
        n
        for n in (await client.get("/api/v1/notes", params={"page_size": 100})).json()["items"]
        if n["series_id"] == series["id"]
    ]
    assert changed_series["version"] == series["version"] + 1
    assert changed_series["tag_ids"] == []
    assert {n["version"] for n in changed_notes} == {2}
    assert all(n["tags"] == [] for n in changed_notes)


async def test_manual_note_api_requires_an_offset_qualified_instant(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/notes",
        json={
            "title": "Naive wall time",
            "starts_at": "2026-10-25T02:30:00",
            "active": True,
            "tag_ids": [],
            "reminder_offsets_minutes": [],
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
