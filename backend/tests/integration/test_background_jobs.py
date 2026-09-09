from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text

from app.db.models import (
    DeliveryState,
    Note,
    NoteTag,
    Notification,
    OutboxEvent,
    ReminderDelivery,
    ReminderRule,
)
from app.db.session import sync_session_factory
from app.email.senders import FakeEmailSender
from app.jobs.maintenance import purge_trash
from app.jobs.outbox import publish_batch
from app.jobs.reminders import authorize_delivery, claim_due, classify_unknown, deliver

pytestmark = pytest.mark.skipif(
    "TEST_DATABASE_URL" not in os.environ,
    reason="set TEST_DATABASE_URL to a migrated PostgreSQL database",
)


@pytest.fixture(autouse=True)
def clean_database() -> None:
    with sync_session_factory() as session, session.begin():
        session.execute(
            text(
                "TRUNCATE outbox_events, notifications, reminder_deliveries, reminder_rules, occurrence_exceptions, series_reminder_templates, series_tags, note_tags, notes, recurrence_series, tags, user_settings CASCADE"
            )
        )


def make_delivery(
    *, due_at: datetime, state: DeliveryState = DeliveryState.pending, claim_expires_at=None
):
    with sync_session_factory() as session, session.begin():
        note = Note(title="Due", body="body", starts_at=due_at + timedelta(minutes=10), active=True)
        session.add(note)
        session.flush()
        rule = ReminderRule(
            note_id=note.id, offset_minutes=10, enabled=True, current_cycle_number=1
        )
        session.add(rule)
        session.flush()
        delivery = ReminderDelivery(
            reminder_rule_id=rule.id,
            cycle_number=1,
            due_at=due_at,
            state=state,
            claim_expires_at=claim_expires_at,
        )
        session.add(delivery)
        session.flush()
        return delivery.id


def test_claim_grace_expiry_authorization_and_duplicate_boundary() -> None:
    now = datetime(2026, 1, 1, 12, tzinfo=UTC)
    missed_id = make_delivery(due_at=now - timedelta(seconds=61))
    due_id = make_delivery(due_at=now - timedelta(seconds=1))
    with sync_session_factory() as session, session.begin():
        claims = claim_due(session, now=now, grace_seconds=60, lease_seconds=30)
    assert [item[0] for item in claims] == [due_id]
    token = claims[0][1]
    with sync_session_factory() as session, session.begin():
        email = authorize_delivery(session, due_id, token, now=now, grace_seconds=60)
    assert email is not None and email.recipient == "demo@example.test"
    with sync_session_factory() as session, session.begin():
        assert authorize_delivery(session, due_id, token, now=now, grace_seconds=60) is None
        assert session.get(ReminderDelivery, missed_id).state == DeliveryState.missed
        assert session.get(ReminderDelivery, due_id).state == DeliveryState.attempt_started
        assert session.scalar(select(func.count()).select_from(Notification)) == 1
        assert (
            session.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.event_type == "notification.created")
            )
            == 1
        )


def test_expired_claim_recovery_unknown_and_outbox_retry() -> None:
    now = datetime(2026, 1, 1, 12, tzinfo=UTC)
    delivery_id = make_delivery(
        due_at=now, state=DeliveryState.claimed, claim_expires_at=now - timedelta(seconds=1)
    )
    with sync_session_factory() as session, session.begin():
        [(claimed_id, token)] = claim_due(session, now=now, grace_seconds=60, lease_seconds=30)
        assert claimed_id == delivery_id
    with sync_session_factory() as session, session.begin():
        authorize_delivery(session, delivery_id, token, now=now, grace_seconds=60)
    with sync_session_factory() as session, session.begin():
        assert classify_unknown(session, now=now + timedelta(seconds=61)) == 1
    with sync_session_factory() as session, session.begin():
        events = list(session.scalars(select(OutboxEvent).order_by(OutboxEvent.created_at)))
        assert len(events) == 2
        event = events[0]
        event_id = str(event.id)

        def fail(channel, payload):
            raise ConnectionError("redis down")

        assert publish_batch(session, fail, now=now) == 0
        assert event.attempts == 1 and event.next_attempt_at == now + timedelta(seconds=1)
        assert event_id in event.payload["event_id"]


def test_purge_redacts_all_content_and_is_idempotent() -> None:
    now = datetime(2026, 2, 1, 12, tzinfo=UTC)
    delivery_id = make_delivery(due_at=now - timedelta(days=40))
    with sync_session_factory() as session, session.begin():
        delivery = session.get(ReminderDelivery, delivery_id)
        rule = session.get(ReminderRule, delivery.reminder_rule_id)
        note = session.get(Note, rule.note_id)
        note.deleted_at = now - timedelta(days=31)
        delivery.recipient_snapshot = "person@example.test"
        delivery.content_snapshot = {"title": "private", "body": "secret"}
        session.add(
            Notification(
                reminder_delivery_id=delivery.id,
                scheduled_at=delivery.due_at,
                title="private",
                body="secret",
            )
        )
        note_id = note.id

    with sync_session_factory() as session, session.begin():
        assert purge_trash(session, now=now) == 1
    with sync_session_factory() as session, session.begin():
        note = session.get(Note, note_id)
        delivery = session.get(ReminderDelivery, delivery_id)
        notification = session.scalars(select(Notification)).one()
        assert (note.title, note.body, note.purged_at) == ("[purged]", "", now)
        assert delivery.recipient_snapshot is None and delivery.content_snapshot is None
        assert (notification.title, notification.body) == ("[purged]", "")
        assert session.scalar(select(func.count()).select_from(NoteTag)) == 0
        event_count = session.scalar(select(func.count()).select_from(OutboxEvent))

    with sync_session_factory() as session, session.begin():
        assert purge_trash(session, now=now + timedelta(hours=1)) == 0
        assert session.scalar(select(func.count()).select_from(OutboxEvent)) == event_count


def test_delivery_attempt_is_at_most_once_and_timeout_is_visible_unknown() -> None:
    now = datetime.now(UTC)
    delivery_id = make_delivery(due_at=now - timedelta(seconds=1))
    with sync_session_factory() as session, session.begin():
        [(_, token)] = claim_due(session, now=now, grace_seconds=60, lease_seconds=30)
    sender = FakeEmailSender(TimeoutError("ambiguous"))
    assert deliver(str(delivery_id), str(token), sender) is False
    assert deliver(str(delivery_id), str(token), sender) is False
    assert len(sender.messages) == 1
    with sync_session_factory() as session, session.begin():
        delivery = session.get(ReminderDelivery, delivery_id)
        notification = session.scalars(select(Notification)).one()
        assert delivery.state == DeliveryState.unknown
        assert notification.title.startswith("[Email outcome unknown]")
        assert (
            session.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.event_type == "notification.created")
            )
            == 2
        )
