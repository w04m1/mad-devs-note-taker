from __future__ import annotations

import hashlib
import os
import uuid
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import UTC, datetime, timedelta
from threading import Event

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
    UserSettings,
)
from app.db.session import sync_session_factory
from app.email.senders import FakeEmailSender
from app.jobs import maintenance, reminders
from app.jobs.maintenance import cleanup_trash, purge_trash
from app.jobs.outbox import publish_batch
from app.jobs.reminders import (
    authorize_delivery,
    claim_due,
    classify_unknown,
    deliver,
    scan_and_enqueue,
)

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        "TEST_DATABASE_URL" not in os.environ,
        reason="set TEST_DATABASE_URL to a migrated PostgreSQL database",
    ),
]


@pytest.fixture(autouse=True)
def clean_database() -> None:
    with sync_session_factory() as session, session.begin():
        session.execute(
            text(
                "TRUNCATE outbox_events, notifications, reminder_deliveries, reminder_rules, occurrence_exceptions, series_reminder_templates, series_tags, note_tags, notes, recurrence_series, tags, user_settings CASCADE"
            )
        )


def make_delivery(
    *,
    due_at: datetime,
    state: DeliveryState = DeliveryState.pending,
    claim_expires_at=None,
    claim_token=None,
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
            claim_token=claim_token,
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


def test_scan_drains_multiple_batches_with_a_stable_grace_cutoff(monkeypatch) -> None:
    now = datetime(2026, 1, 1, 12, tzinfo=UTC)
    with sync_session_factory() as session, session.begin():
        session.execute(
            text(
                """
                INSERT INTO notes
                    (id, title, body, starts_at, active, version, created_at, updated_at)
                SELECT md5('note-' || g)::uuid, 'Due ' || g, '', :starts_at, true, 1, :now, :now
                FROM generate_series(1, 102) AS g
                """
            ),
            {"now": now, "starts_at": now + timedelta(hours=1)},
        )
        session.execute(
            text(
                """
                INSERT INTO reminder_rules
                    (id, note_id, offset_minutes, enabled, current_cycle_number, created_at, updated_at)
                SELECT md5('rule-' || g)::uuid, md5('note-' || g)::uuid,
                       10, true, 1, :now, :now
                FROM generate_series(1, 102) AS g
                """
            ),
            {"now": now},
        )
        session.execute(
            text(
                """
                INSERT INTO reminder_deliveries
                    (id, reminder_rule_id, cycle_number, due_at, state, created_at, updated_at)
                SELECT md5('delivery-' || g)::uuid, md5('rule-' || g)::uuid, 1,
                       CASE WHEN g <= 101 THEN :old_due ELSE :cutoff_due END,
                       'pending'::delivery_state, :now, :now
                FROM generate_series(1, 102) AS g
                """
            ),
            {
                "now": now,
                "old_due": now - timedelta(seconds=120),
                "cutoff_due": now - timedelta(seconds=60),
            },
        )
    monkeypatch.setattr(reminders, "utcnow", lambda: now)
    enqueued: list[tuple[str, str]] = []
    assert scan_and_enqueue(lambda delivery_id, token: enqueued.append((delivery_id, token))) == 1
    assert len(enqueued) == 1
    with sync_session_factory() as session, session.begin():
        states = dict(
            session.execute(
                text(
                    "SELECT due_at, state::text FROM reminder_deliveries "
                    "GROUP BY due_at, state ORDER BY due_at"
                )
            ).all()
        )
        assert states == {
            now - timedelta(seconds=120): "missed",
            now - timedelta(seconds=60): "claimed",
        }
    assert scan_and_enqueue(lambda *_: pytest.fail("rerun must enqueue nothing")) == 0


def test_expired_claim_recovery_unknown_and_outbox_retry() -> None:
    now = datetime(2026, 1, 1, 12, tzinfo=UTC)
    delivery_id = make_delivery(
        due_at=now,
        state=DeliveryState.claimed,
        claim_token=uuid.uuid4(),
        claim_expires_at=now - timedelta(seconds=1),
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
        delivery.state = DeliveryState.sent
        delivery.claim_token = uuid.uuid4()
        delivery.authorized_at = now - timedelta(days=40)
        delivery.result_at = now - timedelta(days=40)
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


def test_cleanup_drains_ten_thousand_and_preserves_ineligible_control(monkeypatch) -> None:
    now = datetime(2026, 2, 1, 12, tzinfo=UTC)
    old = now - timedelta(days=31)
    recent = now - timedelta(days=29)
    with sync_session_factory() as session, session.begin():
        session.execute(
            text(
                """
                INSERT INTO notes
                    (id, title, body, starts_at, active, deleted_at,
                     version, created_at, updated_at)
                SELECT md5('purge-' || g)::uuid, 'private-' || g, 'secret-' || g,
                       :now, true, :old, 1, :now, :now
                FROM generate_series(1, 10000) AS g
                """
            ),
            {"now": now, "old": old},
        )
        session.execute(
            text(
                """
                INSERT INTO notes
                    (id, title, body, starts_at, active, deleted_at,
                     version, created_at, updated_at)
                VALUES (md5('recent-control')::uuid, 'keep me', 'still private',
                        :now, true, :recent, 1, :now, :now)
                """
            ),
            {"now": now, "recent": recent},
        )
    monkeypatch.setattr(maintenance, "utcnow", lambda: now)
    assert cleanup_trash() == 10_000
    with sync_session_factory() as session, session.begin():
        assert (
            session.scalar(select(func.count()).select_from(Note).where(Note.purged_at == now))
            == 10_000
        )
        control = session.get(Note, uuid.UUID(bytes=hashlib.md5(b"recent-control").digest()))
        assert control is not None
        assert (control.title, control.body, control.purged_at) == (
            "keep me",
            "still private",
            None,
        )
    assert cleanup_trash() == 0


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


def test_recipient_authorization_serializes_with_settings_change() -> None:
    now = datetime.now(UTC)
    delivery_id = make_delivery(due_at=now - timedelta(seconds=1))
    with sync_session_factory() as session, session.begin():
        session.add(
            UserSettings(
                id=reminders.PROFILE_ID,
                email="removed@example.test",
                timezone="UTC",
            )
        )
    with sync_session_factory() as session, session.begin():
        [(_, token)] = claim_due(session, now=now, grace_seconds=60, lease_seconds=30)

    sender = FakeEmailSender()
    started = Event()

    def send_after_barrier() -> bool:
        started.set()
        return deliver(str(delivery_id), str(token), sender)

    with ThreadPoolExecutor(max_workers=1) as pool:
        with sync_session_factory() as session, session.begin():
            settings = session.scalars(
                select(UserSettings)
                .where(UserSettings.id == reminders.PROFILE_ID)
                .with_for_update()
            ).one()
            settings.email = "current@example.test"
            session.flush()
            future = pool.submit(send_after_barrier)
            assert started.wait(timeout=2)
            assert not wait([future], timeout=0.25).done
        assert future.result(timeout=5) is True

    assert [message.recipient for message in sender.messages] == ["current@example.test"]
    assert all(message.recipient != "removed@example.test" for message in sender.messages)
