from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import text

from app.api import router as api_router
from app.config import Settings, get_settings
from app.db.session import async_engine, sync_session_factory
from app.email.senders import FakeEmailSender
from app.jobs.maintenance import purge_trash
from app.jobs.reminders import deliver
from app.main import app

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        "TEST_DATABASE_URL" not in os.environ,
        reason="set TEST_DATABASE_URL to a migrated PostgreSQL database",
    ),
]


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


async def test_upcoming_shared_pager_reaches_every_group_boundary(
    client: httpx.AsyncClient, monkeypatch
) -> None:
    now = datetime(2026, 1, 5, 10, tzinfo=UTC)
    monkeypatch.setattr(api_router, "utcnow", lambda: now)
    async with async_engine.begin() as connection:
        await connection.execute(
            text(
                """
                INSERT INTO notes
                    (id, title, body, starts_at, active, version, created_at, updated_at)
                SELECT md5(kind || '-' || g)::uuid, kind || '-' || g, '',
                       CASE kind
                         WHEN 'past' THEN CAST(:now AS timestamptz) - interval '2 hours' + g * interval '1 second'
                         WHEN 'today' THEN CAST(:now AS timestamptz) + interval '1 hour' + g * interval '1 second'
                         ELSE CAST(:now AS timestamptz) + interval '2 days' + g * interval '1 second'
                       END,
                       true, 1, :now, :now
                FROM unnest(ARRAY['past', 'today', 'week']) AS categories(kind)
                CROSS JOIN generate_series(1, 51) AS g
                """
            ),
            {"now": now},
        )
    first = (await client.get("/api/v1/upcoming", params={"page": 1, "page_size": 50})).json()
    second = (await client.get("/api/v1/upcoming", params={"page": 2, "page_size": 50})).json()
    third = (await client.get("/api/v1/upcoming", params={"page": 3, "page_size": 50})).json()
    for group in ("today", "week", "past"):
        assert (first[group]["total"], second[group]["total"], third[group]["total"]) == (
            51,
            51,
            51,
        )
        assert len(first[group]["items"]) == 50
        assert len(second[group]["items"]) == 1
        assert third[group]["items"] == []
        assert first[group]["page"] == 1
        assert second[group]["page"] == 2
        assert third[group]["page"] == 3


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
    first: datetime,
    *,
    title: str = "Contract series",
    tag_ids=None,
    reminders=None,
    end_days: int = 2,
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
        "end_date": (first.date() + timedelta(days=end_days)).isoformat(),
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


async def test_split_rejects_overlap_with_immutable_trash_action(
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
    assert split.status_code == 409, split.text
    assert split.json()["code"] == "trash_action_overlap"
    groups = (await client.get("/api/v1/trash/groups", params={"page_size": 100})).json()
    assert groups["total"] == 1
    assert groups["items"][0]["kind"] == "series_action"
    assert groups["items"][0]["count"] == 2


async def test_two_recurring_trash_actions_are_stable_and_restore_independently(
    client: httpx.AsyncClient,
) -> None:
    first = (datetime.now(UTC) + timedelta(days=85)).replace(microsecond=0)
    series = (await client.post("/api/v1/series", json=_series_payload(first))).json()
    notes = sorted(
        (await client.get("/api/v1/notes", params={"page_size": 100})).json()["items"],
        key=lambda note: note["recurrence_key"],
    )
    assert (
        await client.post(
            f"/api/v1/series/{series['id']}/trash",
            json={
                "expected_series_version": series["version"],
                "recurrence_key": notes[2]["recurrence_key"],
            },
        )
    ).status_code == 204
    assert (
        await client.post(
            f"/api/v1/series/{series['id']}/trash",
            json={
                "expected_series_version": series["version"] + 1,
                "recurrence_key": notes[0]["recurrence_key"],
            },
        )
    ).status_code == 204

    groups = (await client.get("/api/v1/trash/groups", params={"page_size": 1})).json()
    next_page = (
        await client.get("/api/v1/trash/groups", params={"page": 2, "page_size": 1})
    ).json()
    empty_page = (
        await client.get("/api/v1/trash/groups", params={"page": 3, "page_size": 1})
    ).json()
    cards = groups["items"] + next_page["items"]
    assert groups["total"] == next_page["total"] == empty_page["total"] == 2
    assert empty_page["items"] == []
    assert {card["count"] for card in cards} == {1, 2}
    assert {card["preview"]["id"] for card in cards} == {notes[0]["id"], notes[2]["id"]}

    ambiguous_alias = await client.post(
        f"/api/v1/series/{series['id']}/restore",
        json={"expected_series_version": series["version"] + 2},
    )
    assert ambiguous_alias.status_code == 409
    one_member = next(card for card in cards if card["count"] == 1)
    restored = await client.post(
        f"/api/v1/trash/actions/{one_member['action_id']}/restore",
        json={"expected_series_version": series["version"] + 2},
    )
    assert restored.status_code == 200, restored.text
    remaining = (await client.get("/api/v1/trash/groups")).json()
    assert remaining["total"] == 1
    assert remaining["items"][0]["count"] == 2

    selected = remaining["items"][0]["preview"]
    alias_restore = await client.post(
        f"/api/v1/notes/{selected['id']}/restore",
        json={
            "expected_version": selected["version"],
            "expected_series_version": restored.json()["version"],
        },
    )
    assert alias_restore.status_code == 200, alias_restore.text
    visible = (await client.get("/api/v1/notes", params={"page_size": 100})).json()["items"]
    assert {note["id"] for note in visible} == {note["id"] for note in notes}
    assert (await client.get("/api/v1/trash/groups")).json()["total"] == 0


async def test_cleanup_never_partly_purges_action_larger_than_batch(
    client: httpx.AsyncClient,
) -> None:
    first = (datetime.now(UTC) + timedelta(days=86)).replace(microsecond=0)
    series = (await client.post("/api/v1/series", json=_series_payload(first, end_days=100))).json()
    trashed = await client.post(
        f"/api/v1/series/{series['id']}/trash",
        json={"expected_series_version": series["version"]},
    )
    assert trashed.status_code == 204, trashed.text
    purge_now = datetime.now(UTC).replace(microsecond=0)
    async with async_engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE notes SET deleted_at=:cutoff "
                "WHERE current_recurring_trash_action_id IS NOT NULL"
            ),
            {"cutoff": purge_now - timedelta(days=30)},
        )
    with sync_session_factory() as session, session.begin():
        assert purge_trash(session, now=purge_now, limit=100) == 101
    async with async_engine.connect() as connection:
        purged, current = (
            await connection.execute(
                text(
                    "SELECT count(*) FILTER (WHERE purged_at IS NOT NULL), "
                    "count(*) FILTER (WHERE current_recurring_trash_action_id IS NOT NULL) "
                    "FROM notes WHERE series_id=:series_id"
                ),
                {"series_id": series["id"]},
            )
        ).one()
    assert (purged, current) == (101, 0)
    assert (await client.get(f"/api/v1/series/{series['id']}")).status_code == 404


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

    ghost = notes[1]
    assert (await client.get(f"/api/v1/notes/{ghost['id']}")).status_code == 404
    assert (
        await client.post(
            f"/api/v1/notes/{ghost['id']}/restore",
            json={
                "expected_version": ghost["version"] + 1,
                "expected_series_version": successor["version"],
            },
        )
    ).status_code == 404
    assert (
        await client.patch(
            f"/api/v1/notes/{ghost['id']}",
            json={
                "title": "Ghost edit",
                "body": "must not send",
                "starts_at": ghost["starts_at"],
                "active": True,
                "tag_ids": [],
                "reminder_offsets_minutes": [10],
                "expected_version": ghost["version"] + 1,
                "expected_series_version": successor["version"],
            },
        )
    ).status_code == 404

    token = uuid.uuid4()
    authorization_now = datetime.now(UTC)
    async with async_engine.begin() as connection:
        delivery_id = (
            await connection.execute(
                text(
                    "SELECT rd.id FROM reminder_deliveries rd "
                    "JOIN reminder_rules rr ON rr.id=rd.reminder_rule_id "
                    "WHERE rr.note_id=:note_id"
                ),
                {"note_id": ghost["id"]},
            )
        ).scalar_one()
        await connection.execute(
            text(
                "UPDATE reminder_deliveries SET state='claimed', due_at=:due_at, "
                "claim_token=:token, claim_expires_at=:expires, result_at=NULL, "
                "authorized_at=NULL, recipient_snapshot=NULL, content_snapshot=NULL, error_code=NULL "
                "WHERE id=:delivery_id"
            ),
            {
                "delivery_id": delivery_id,
                "due_at": authorization_now - timedelta(seconds=1),
                "expires": authorization_now + timedelta(seconds=30),
                "token": token,
            },
        )
        before_notifications = (
            await connection.execute(text("SELECT count(*) FROM notifications"))
        ).scalar_one()
        before_outbox = (
            await connection.execute(text("SELECT count(*) FROM outbox_events"))
        ).scalar_one()
    sender = FakeEmailSender()
    assert deliver(str(delivery_id), str(token), sender) is False
    assert sender.messages == []
    async with async_engine.connect() as connection:
        state = (
            await connection.execute(
                text("SELECT state::text FROM reminder_deliveries WHERE id=:delivery_id"),
                {"delivery_id": delivery_id},
            )
        ).scalar_one()
        assert state == "cancelled"
        assert (
            await connection.execute(text("SELECT count(*) FROM notifications"))
        ).scalar_one() == before_notifications
        assert (
            await connection.execute(text("SELECT count(*) FROM outbox_events"))
        ).scalar_one() == before_outbox


async def test_split_rejects_preserved_key_collision_and_generated_historical_instants(
    client: httpx.AsyncClient,
) -> None:
    first = (datetime.now(UTC) + timedelta(days=180)).replace(microsecond=0)
    series = (await client.post("/api/v1/series", json=_series_payload(first))).json()
    notes = (await client.get("/api/v1/notes", params={"page_size": 100})).json()["items"]
    notes = sorted(
        (note for note in notes if note["series_id"] == series["id"]),
        key=lambda note: note["recurrence_key"],
    )

    collision_payload = {
        **_series_payload(first, title="Collision"),
        "recurrence_key": notes[1]["recurrence_key"],
        "expected_version": series["version"],
        "expected_occurrence_version": notes[1]["version"],
    }
    collision = await client.post(f"/api/v1/series/{series['id']}/split", json=collision_payload)
    assert collision.status_code == 409, collision.text
    assert collision.json()["code"] == "recurrence_collision"
    assert datetime.fromisoformat(collision.json()["current"]["recurrence_keys"][0]) == first

    effective_collision = first + timedelta(days=1, hours=2)
    moved = await client.patch(
        f"/api/v1/notes/{notes[0]['id']}",
        json={
            "title": notes[0]["title"],
            "body": notes[0]["body"],
            "starts_at": effective_collision.isoformat(),
            "active": notes[0]["active"],
            "tag_ids": [],
            "reminder_offsets_minutes": [],
            "expected_version": notes[0]["version"],
            "expected_series_version": series["version"],
        },
    )
    assert moved.status_code == 200, moved.text
    effective_payload = {
        **_series_payload(effective_collision, title="Effective collision"),
        "recurrence_key": notes[1]["recurrence_key"],
        "expected_version": series["version"] + 1,
        "expected_occurrence_version": notes[1]["version"],
    }
    effective = await client.post(f"/api/v1/series/{series['id']}/split", json=effective_payload)
    assert effective.status_code == 409, effective.text
    assert effective.json()["code"] == "recurrence_collision"
    assert effective.json()["current"]["note_ids"] == [notes[0]["id"]]
    assert effective.json()["current"]["starts_at"] == [effective_collision.isoformat()]

    past = (datetime.now(UTC) - timedelta(days=2)).replace(microsecond=0)
    historical_payload = {
        **_series_payload(past, title="Historical"),
        "recurrence_key": notes[1]["recurrence_key"],
        "expected_version": series["version"] + 1,
        "expected_occurrence_version": notes[1]["version"],
    }
    historical = await client.post(f"/api/v1/series/{series['id']}/split", json=historical_payload)
    assert historical.status_code == 409, historical.text
    assert historical.json()["code"] == "historical_replacement"

    async with async_engine.connect() as connection:
        series_rows = (
            await connection.execute(
                text(
                    "SELECT count(*), max(split_boundary) FROM recurrence_series "
                    "WHERE lineage_id=:lineage_id"
                ),
                {"lineage_id": series["lineage_id"]},
            )
        ).one()
        note_count = (
            await connection.execute(
                text("SELECT count(*) FROM notes WHERE series_id=:series_id"),
                {"series_id": series["id"]},
            )
        ).scalar_one()
    assert series_rows == (1, None)
    assert note_count == 3
    unchanged = (await client.get(f"/api/v1/series/{series['id']}")).json()
    assert unchanged["version"] == series["version"] + 1


async def test_repeated_predecessor_split_is_atomic_and_leaf_successor_can_split(
    client: httpx.AsyncClient,
) -> None:
    first = (datetime.now(UTC) + timedelta(days=185)).replace(microsecond=0)
    original = (await client.post("/api/v1/series", json=_series_payload(first))).json()
    original_notes = (await client.get("/api/v1/notes", params={"page_size": 100})).json()["items"]
    original_notes = sorted(
        (note for note in original_notes if note["series_id"] == original["id"]),
        key=lambda note: note["recurrence_key"],
    )
    first_payload = {
        **_series_payload(first + timedelta(days=1), title="First successor"),
        "recurrence_key": original_notes[1]["recurrence_key"],
        "expected_version": original["version"],
        "expected_occurrence_version": original_notes[1]["version"],
    }
    first_split = await client.post(f"/api/v1/series/{original['id']}/split", json=first_payload)
    assert first_split.status_code == 200, first_split.text
    successor = first_split.json()

    async def lineage_state() -> tuple[int, int, int]:
        async with async_engine.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        """
                        SELECT count(DISTINCT rs.id),
                               count(n.id),
                               count(n.id) - count(DISTINCT n.recurrence_key)
                        FROM recurrence_series rs
                        LEFT JOIN notes n
                          ON n.series_id = rs.id AND n.superseded_at IS NULL
                        WHERE rs.lineage_id = :lineage_id
                        """
                    ),
                    {"lineage_id": original["lineage_id"]},
                )
            ).one()
        return row[0], row[1], row[2]

    before_retry = await lineage_state()
    repeated = await client.post(f"/api/v1/series/{original['id']}/split", json=first_payload)
    assert repeated.status_code == 409, repeated.text
    assert repeated.json()["code"] == "series_not_leaf"
    assert repeated.json()["current"]["successor_id"] == successor["id"]
    assert await lineage_state() == before_retry
    assert before_retry[2] == 0

    successor_notes = (await client.get("/api/v1/notes", params={"page_size": 100})).json()["items"]
    successor_notes = sorted(
        (note for note in successor_notes if note["series_id"] == successor["id"]),
        key=lambda note: note["recurrence_key"],
    )
    leaf_boundary = datetime.fromisoformat(successor_notes[1]["recurrence_key"])
    leaf_payload = {
        **_series_payload(leaf_boundary, title="Second successor"),
        "recurrence_key": successor_notes[1]["recurrence_key"],
        "expected_version": successor["version"],
        "expected_occurrence_version": successor_notes[1]["version"],
    }
    second_split = await client.post(f"/api/v1/series/{successor['id']}/split", json=leaf_payload)
    assert second_split.status_code == 200, second_split.text
    assert second_split.json()["predecessor_id"] == successor["id"]
    assert second_split.json()["lineage_id"] == original["lineage_id"]
    final_state = await lineage_state()
    assert final_state[0] == 3
    assert final_state[2] == 0


async def test_leaf_split_backward_shift_collision_is_atomic(
    client: httpx.AsyncClient,
) -> None:
    first = (datetime.now(UTC) + timedelta(days=190)).replace(microsecond=0)
    original = (await client.post("/api/v1/series", json=_series_payload(first))).json()
    notes = (await client.get("/api/v1/notes", params={"page_size": 100})).json()["items"]
    notes = sorted(
        (note for note in notes if note["series_id"] == original["id"]),
        key=lambda note: note["recurrence_key"],
    )
    first_split_payload = {
        **_series_payload(first + timedelta(days=1), title="Middle segment"),
        "end_date": (first.date() + timedelta(days=2)).isoformat(),
        "recurrence_key": notes[1]["recurrence_key"],
        "expected_version": original["version"],
        "expected_occurrence_version": notes[1]["version"],
    }
    first_split = await client.post(
        f"/api/v1/series/{original['id']}/split", json=first_split_payload
    )
    assert first_split.status_code == 200, first_split.text
    successor = first_split.json()
    current = (await client.get("/api/v1/notes", params={"page_size": 100})).json()["items"]
    current = sorted(
        (note for note in current if note["series_id"] == successor["id"]),
        key=lambda note: note["recurrence_key"],
    )

    collision_payload = {
        **_series_payload(first, title="Must not overlap predecessor"),
        "end_date": first.date().isoformat(),
        "recurrence_key": current[1]["recurrence_key"],
        "expected_version": successor["version"],
        "expected_occurrence_version": current[1]["version"],
    }
    collision = await client.post(f"/api/v1/series/{successor['id']}/split", json=collision_payload)
    assert collision.status_code == 409, collision.text
    assert collision.json()["code"] == "recurrence_collision"
    assert collision.json()["current"]["note_ids"] == [notes[0]["id"]]
    async with async_engine.connect() as connection:
        lineage_count = (
            await connection.execute(
                text("SELECT count(*) FROM recurrence_series WHERE lineage_id=:lineage_id"),
                {"lineage_id": original["lineage_id"]},
            )
        ).scalar_one()
    assert lineage_count == 2
    unchanged = (await client.get(f"/api/v1/series/{successor['id']}")).json()
    assert unchanged["split_boundary"] is None
    assert unchanged["version"] == successor["version"]


async def test_split_preserves_purged_tombstone_and_materializes_accessible_replacement(
    client: httpx.AsyncClient,
) -> None:
    first = (datetime.now(UTC) + timedelta(days=200)).replace(microsecond=0)
    series = (await client.post("/api/v1/series", json=_series_payload(first))).json()
    notes = (await client.get("/api/v1/notes", params={"page_size": 100})).json()["items"]
    notes = sorted(
        (note for note in notes if note["series_id"] == series["id"]),
        key=lambda note: note["recurrence_key"],
    )
    tombstone = notes[1]
    deleted = await client.delete(
        f"/api/v1/notes/{tombstone['id']}",
        params={
            "expected_version": tombstone["version"],
            "expected_series_version": series["version"],
        },
    )
    assert deleted.status_code == 204, deleted.text
    purge_now = datetime.now(UTC).replace(microsecond=0)
    async with async_engine.begin() as connection:
        await connection.execute(
            text("UPDATE notes SET deleted_at=:deleted_at WHERE id=:note_id"),
            {"deleted_at": purge_now - timedelta(days=31), "note_id": tombstone["id"]},
        )
    with sync_session_factory() as session, session.begin():
        assert purge_trash(session, now=purge_now) == 1

    split_payload = {
        **_series_payload(first, title="Replacement"),
        "recurrence_key": notes[0]["recurrence_key"],
        "expected_version": series["version"] + 1,
        "expected_occurrence_version": notes[0]["version"],
    }
    split = await client.post(f"/api/v1/series/{series['id']}/split", json=split_payload)
    assert split.status_code == 200, split.text
    successor = split.json()

    listed = (await client.get("/api/v1/notes", params={"page_size": 100})).json()["items"]
    replacement = next(
        note for note in listed if note["recurrence_key"] == tombstone["recurrence_key"]
    )
    assert replacement["id"] != tombstone["id"]
    assert replacement["series_id"] == successor["id"]
    assert tombstone["id"] not in {note["id"] for note in listed}
    trash = (await client.get("/api/v1/notes", params={"trash": True})).json()["items"]
    assert tombstone["id"] not in {note["id"] for note in trash}

    calendar = await client.get(
        "/api/v1/calendar",
        params={
            "starts_from": (first - timedelta(days=1)).isoformat(),
            "starts_to": (first + timedelta(days=4)).isoformat(),
        },
    )
    assert calendar.status_code == 200, calendar.text
    calendar_ids = {note["id"] for note in calendar.json()}
    assert replacement["id"] in calendar_ids
    assert tombstone["id"] not in calendar_ids
    assert (await client.get(f"/api/v1/notes/{tombstone['id']}")).status_code == 404
    invalid_edit = await client.patch(
        f"/api/v1/notes/{tombstone['id']}",
        json={
            "title": "Must stay gone",
            "body": "",
            "starts_at": tombstone["starts_at"],
            "active": True,
            "tag_ids": [],
            "reminder_offsets_minutes": [],
            "expected_version": tombstone["version"],
            "expected_series_version": successor["version"],
        },
    )
    assert invalid_edit.status_code == 404

    detail = await client.get(f"/api/v1/notes/{replacement['id']}")
    assert detail.status_code == 200
    editable = detail.json()
    edited = await client.patch(
        f"/api/v1/notes/{replacement['id']}",
        json={
            "title": "Editable replacement",
            "body": editable["body"],
            "starts_at": editable["starts_at"],
            "active": editable["active"],
            "tag_ids": [],
            "reminder_offsets_minutes": [],
            "expected_version": editable["version"],
            "expected_series_version": successor["version"],
        },
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["title"] == "Editable replacement"

    async with async_engine.connect() as connection:
        stored = (
            await connection.execute(
                text(
                    "SELECT purged_at IS NOT NULL, superseded_at IS NOT NULL, title, series_id::text "
                    "FROM notes WHERE id=:note_id"
                ),
                {"note_id": tombstone["id"]},
            )
        ).one()
        marker = (
            await connection.execute(
                text(
                    "SELECT cancelled, overridden_fields FROM occurrence_exceptions "
                    "WHERE series_id=:series_id AND recurrence_key=:recurrence_key"
                ),
                {
                    "series_id": series["id"],
                    "recurrence_key": datetime.fromisoformat(tombstone["recurrence_key"]),
                },
            )
        ).one()
    # Purged rows are immutable; the later split leaves this technical tombstone
    # on its original segment rather than adding a superseded marker.
    assert stored == (True, False, "[purged]", series["id"])
    assert marker == (True, {})


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
