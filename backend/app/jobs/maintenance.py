from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import (
    Note,
    NoteTag,
    Notification,
    OccurrenceException,
    OutboxEvent,
    RecurrenceSeries,
    ReminderDelivery,
    ReminderRule,
)
from app.db.session import sync_session_factory
from app.jobs.reminders import classify_unknown


def utcnow() -> datetime:
    return datetime.now(UTC)


def purge_trash(
    session: Session, *, now: datetime, retention_days: int = 30, limit: int = 100
) -> int:
    cutoff = now - timedelta(days=retention_days)
    candidates = session.execute(
        select(Note.id, Note.series_id)
        .where(Note.deleted_at <= cutoff, Note.purged_at.is_(None))
        .order_by(Note.id)
        .limit(limit)
    ).all()
    series_ids = sorted({sid for _, sid in candidates if sid is not None})
    note_ids = sorted(nid for nid, _ in candidates)
    if series_ids:
        list(
            session.scalars(
                select(RecurrenceSeries)
                .where(RecurrenceSeries.id.in_(series_ids))
                .order_by(RecurrenceSeries.id)
                .with_for_update()
            )
        )
    notes = (
        list(
            session.scalars(
                select(Note)
                .where(
                    Note.id.in_(note_ids),
                    Note.deleted_at <= cutoff,
                    Note.purged_at.is_(None),
                )
                .order_by(Note.id)
                .with_for_update()
            )
        )
        if note_ids
        else []
    )
    for note in notes:
        note.title, note.body, note.purged_at, note.updated_at = "[purged]", "", now, now
        rule_ids = select(ReminderRule.id).where(ReminderRule.note_id == note.id)
        delivery_ids = select(ReminderDelivery.id).where(
            ReminderDelivery.reminder_rule_id.in_(rule_ids)
        )
        session.execute(
            ReminderDelivery.__table__.update()
            .where(ReminderDelivery.id.in_(delivery_ids))
            .values(content_snapshot=None, recipient_snapshot=None)
        )
        session.execute(
            Notification.__table__.update()
            .where(Notification.reminder_delivery_id.in_(delivery_ids))
            .values(title="[purged]", body="")
        )
        session.execute(NoteTag.__table__.delete().where(NoteTag.note_id == note.id))
        if note.series_id is not None and note.recurrence_key is not None:
            session.execute(
                OccurrenceException.__table__.update()
                .where(
                    OccurrenceException.series_id == note.series_id,
                    OccurrenceException.recurrence_key == note.recurrence_key,
                )
                .values(overridden_fields={})
            )
    session.flush()
    for note in notes:
        event_id = uuid.uuid4()
        session.add(
            OutboxEvent(
                id=event_id,
                event_type="note.deleted",
                entity_id=note.id,
                payload={
                    "event_id": str(event_id),
                    "type": "note.deleted",
                    "occurred_at": now.isoformat(),
                    "entity_id": str(note.id),
                    "version": note.version,
                    "series_id": str(note.series_id) if note.series_id else None,
                },
            )
        )
    return len(notes)


def cleanup_trash() -> int:
    with sync_session_factory() as session, session.begin():
        return purge_trash(session, now=utcnow())


def maintain() -> int:
    now = utcnow()
    with sync_session_factory() as session, session.begin():
        changed = classify_unknown(session, now=now)
        # Notification history is explicitly 30 days. Published outbox rows
        # have no replay role and follow the same retention period.
        session.execute(
            delete(Notification).where(Notification.created_at < now - timedelta(days=30))
        )
        session.execute(
            delete(OutboxEvent).where(OutboxEvent.published_at < now - timedelta(days=30))
        )
        return changed
