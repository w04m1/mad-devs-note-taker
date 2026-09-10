from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, exists, insert, literal_column, select
from sqlalchemy.orm import Session

from app.db.models import (
    Note,
    NoteTag,
    Notification,
    OccurrenceException,
    OutboxEvent,
    RecurrenceSeries,
    RecurringTrashAction,
    RecurringTrashActionMember,
    ReminderDelivery,
    ReminderRule,
    SeriesReminderTemplate,
    SeriesTag,
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
        select(Note.id, Note.series_id, Note.current_recurring_trash_action_id)
        .where(Note.deleted_at <= cutoff, Note.purged_at.is_(None))
        .order_by(Note.id)
        .limit(limit)
    ).all()
    action_ids = sorted({aid for _, _, aid in candidates if aid is not None})
    if action_ids:
        action_member_rows = session.execute(
            select(
                RecurringTrashActionMember.note_id,
                Note.series_id,
                RecurringTrashActionMember.action_id,
            )
            .join(Note, Note.id == RecurringTrashActionMember.note_id)
            .where(
                RecurringTrashActionMember.action_id.in_(action_ids),
                Note.current_recurring_trash_action_id == RecurringTrashActionMember.action_id,
            )
        ).all()
        candidates = list(candidates) + list(action_member_rows)
    # The same note can be selected directly and through its action membership.
    # Preserve deterministic ordering while processing it exactly once.
    candidates = list(dict.fromkeys(candidates))
    series_ids = sorted({sid for _, sid, _ in candidates if sid is not None})
    note_ids = sorted({nid for nid, _, _ in candidates})
    if series_ids:
        list(
            session.scalars(
                select(RecurrenceSeries)
                .where(RecurrenceSeries.id.in_(series_ids))
                .order_by(RecurrenceSeries.id)
                .with_for_update()
            )
        )
    if action_ids:
        list(
            session.scalars(
                select(RecurringTrashAction)
                .where(RecurringTrashAction.id.in_(action_ids))
                .order_by(RecurringTrashAction.id)
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
    purged_note_ids = [note.id for note in notes]
    for note in notes:
        note.title, note.body, note.purged_at, note.updated_at = "[purged]", "", now, now
        note.current_recurring_trash_action_id = None
    if purged_note_ids:
        rule_ids = select(ReminderRule.id).where(ReminderRule.note_id.in_(purged_note_ids))
        delivery_ids = select(ReminderDelivery.id).where(
            ReminderDelivery.reminder_rule_id.in_(rule_ids)
        )
        session.execute(
            ReminderDelivery.__table__.update()
            .where(ReminderDelivery.id.in_(delivery_ids))
            .values(content_snapshot=literal_column("NULL"), recipient_snapshot=None)
        )
        session.execute(
            Notification.__table__.update()
            .where(Notification.reminder_delivery_id.in_(delivery_ids))
            .values(title="[purged]", body="")
        )
        session.execute(NoteTag.__table__.delete().where(NoteTag.note_id.in_(purged_note_ids)))
        matching_note = select(Note.id).where(
            Note.id.in_(purged_note_ids),
            Note.series_id == OccurrenceException.series_id,
            Note.recurrence_key == OccurrenceException.recurrence_key,
        )
        session.execute(
            OccurrenceException.__table__.update()
            .where(exists(matching_note))
            .values(overridden_fields={})
        )
    session.flush()
    for series_id in series_ids:
        has_unpurged_note = session.execute(
            select(Note.id).where(Note.series_id == series_id, Note.purged_at.is_(None)).limit(1)
        ).first()
        if has_unpurged_note is None:
            series = session.get(RecurrenceSeries, series_id)
            if series is not None and series.purged_at is None:
                session.execute(
                    SeriesTag.__table__.delete().where(SeriesTag.series_id == series_id)
                )
                session.execute(
                    SeriesReminderTemplate.__table__.delete().where(
                        SeriesReminderTemplate.series_id == series_id
                    )
                )
                session.execute(
                    OccurrenceException.__table__.update()
                    .where(OccurrenceException.series_id == series_id)
                    .values(cancelled=True, overridden_fields={})
                )
                series.local_start = datetime(1970, 1, 1, tzinfo=UTC).replace(tzinfo=None)
                series.timezone = "UTC"
                series.rrule = "FREQ=DAILY;INTERVAL=1"
                series.end_date = date(1970, 1, 1)
                series.template_title = "[purged]"
                series.template_body = ""
                series.template_active = False
                series.purged_at = now
    session.flush()
    events = []
    for note in notes:
        event_id = uuid.uuid4()
        events.append(
            {
                "id": event_id,
                "event_type": "note.deleted",
                "entity_id": note.id,
                "payload": {
                    "event_id": str(event_id),
                    "type": "note.deleted",
                    "occurred_at": now.isoformat(),
                    "entity_id": str(note.id),
                    "version": note.version,
                    "series_id": str(note.series_id) if note.series_id else None,
                },
            }
        )
    if events:
        session.execute(insert(OutboxEvent), events)
    return len(notes)


def cleanup_trash() -> int:
    cleanup_now = utcnow()
    total = 0
    while True:
        with sync_session_factory() as session, session.begin():
            changed = purge_trash(session, now=cleanup_now, limit=10_000)
        total += changed
        if changed < 10_000:
            return total


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
