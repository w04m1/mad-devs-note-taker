from __future__ import annotations

import smtplib
import socket
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import (
    DeliveryState,
    Note,
    Notification,
    OutboxEvent,
    RecurrenceSeries,
    ReminderDelivery,
    ReminderRule,
    UserSettings,
)
from app.db.session import sync_session_factory
from app.email.senders import Email, EmailSender, SMTPEmailSender

PROFILE_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def utcnow() -> datetime:
    return datetime.now(UTC)


def claim_due(
    session: Session, *, now: datetime, grace_seconds: int, lease_seconds: int, limit: int = 100
) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """Claim a bounded batch. Enqueue only after the caller commits."""
    expired = or_(
        ReminderDelivery.state == DeliveryState.pending,
        (ReminderDelivery.state == DeliveryState.claimed)
        & (ReminderDelivery.claim_expires_at <= now),
    )
    rows = list(
        session.scalars(
            select(ReminderDelivery)
            .where(expired, ReminderDelivery.due_at <= now)
            .order_by(ReminderDelivery.due_at, ReminderDelivery.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )
    claimed: list[tuple[uuid.UUID, uuid.UUID]] = []
    cutoff = now - timedelta(seconds=grace_seconds)
    for delivery in rows:
        if delivery.due_at < cutoff:
            delivery.state = DeliveryState.missed
            delivery.claim_token = delivery.claim_expires_at = None
            delivery.result_at = now
        else:
            token = uuid.uuid4()
            delivery.state = DeliveryState.claimed
            delivery.claim_token = token
            delivery.claim_expires_at = now + timedelta(seconds=lease_seconds)
            claimed.append((delivery.id, token))
    return claimed


def scan_and_enqueue(enqueue: Callable[[str, str], object]) -> int:
    settings = get_settings()
    with sync_session_factory() as session, session.begin():
        claims = claim_due(
            session,
            now=utcnow(),
            grace_seconds=settings.reminder_grace_seconds,
            lease_seconds=settings.reminder_claim_seconds,
        )
    # Failed enqueue is deliberately not rolled back: the lease recovers it.
    for delivery_id, token in claims:
        try:
            enqueue(str(delivery_id), str(token))
        except Exception:  # noqa: BLE001, S112
            continue
    return len(claims)


def authorize_delivery(
    session: Session, delivery_id: uuid.UUID, token: uuid.UUID, *, now: datetime, grace_seconds: int
) -> Email | None:
    """Final authorization boundary. Lock order: series, note, rule, delivery."""
    ids = session.execute(
        select(ReminderDelivery.reminder_rule_id, ReminderRule.note_id, Note.series_id)
        .join(ReminderRule, ReminderRule.id == ReminderDelivery.reminder_rule_id)
        .join(Note, Note.id == ReminderRule.note_id)
        .where(ReminderDelivery.id == delivery_id)
    ).one_or_none()
    if ids is None:
        return None
    rule_id, note_id, series_id = ids
    if series_id is not None:
        session.execute(
            select(RecurrenceSeries.id).where(RecurrenceSeries.id == series_id).with_for_update()
        ).one()
    note = session.scalars(select(Note).where(Note.id == note_id).with_for_update()).one()
    rule = session.scalars(
        select(ReminderRule).where(ReminderRule.id == rule_id).with_for_update()
    ).one()
    delivery = session.scalars(
        select(ReminderDelivery).where(ReminderDelivery.id == delivery_id).with_for_update()
    ).one()
    if delivery.state != DeliveryState.claimed or delivery.claim_token != token:
        return None
    if (
        not rule.enabled
        or rule.current_cycle_number != delivery.cycle_number
        or not note.active
        or note.deleted_at is not None
    ):
        delivery.state = DeliveryState.cancelled
        delivery.claim_token = delivery.claim_expires_at = None
        delivery.result_at = now
        return None
    if delivery.due_at > now:
        delivery.state = DeliveryState.pending
        delivery.claim_token = delivery.claim_expires_at = None
        return None
    if delivery.due_at < now - timedelta(seconds=grace_seconds):
        delivery.state = DeliveryState.missed
        delivery.claim_token = delivery.claim_expires_at = None
        delivery.result_at = now
        return None
    settings = session.get(UserSettings, PROFILE_ID)
    recipient = settings.email.strip() if settings else get_settings().app_default_email.strip()
    delivery.state = DeliveryState.attempt_started
    delivery.authorized_at = now
    delivery.claim_expires_at = None
    delivery.recipient_snapshot = recipient
    delivery.content_snapshot = {"title": note.title, "body": note.body, "note_id": str(note.id)}
    notification_id = uuid.uuid4()
    session.add(
        Notification(
            id=notification_id,
            reminder_delivery_id=delivery.id,
            scheduled_at=delivery.due_at,
            title=note.title,
            body=note.body,
        )
    )
    event_id = uuid.uuid4()
    session.add(
        OutboxEvent(
            id=event_id,
            event_type="notification.created",
            entity_id=notification_id,
            payload={
                "event_id": str(event_id),
                "type": "notification.created",
                "occurred_at": now.isoformat(),
                "entity_id": str(notification_id),
                "notification_id": str(notification_id),
                "version": 1,
                "series_id": str(series_id) if series_id else None,
            },
        )
    )
    return Email(
        recipient=recipient,
        subject=f"Reminder: {note.title}",
        body=note.body,
        message_id=f"<{delivery.id}.{delivery.cycle_number}@notetaker.local>",
    )


def smtp_sender() -> SMTPEmailSender:
    s = get_settings()
    return SMTPEmailSender(
        host=s.smtp_host,
        port=s.smtp_port,
        sender=s.smtp_from,
        username=s.smtp_username,
        password=s.smtp_password,
        starttls=s.smtp_starttls,
        timeout=s.smtp_timeout_seconds,
    )


def _valid_recipient(recipient: str) -> bool:
    local, separator, domain = recipient.strip().partition("@")
    return bool(local and separator and domain and not any(char.isspace() for char in recipient))


def _ambiguous_smtp_error(exc: Exception) -> bool:
    # A timeout/disconnect can happen after the SMTP server accepted DATA.
    return isinstance(exc, (TimeoutError, socket.timeout, smtplib.SMTPServerDisconnected))


def _record_visible_email_failure(
    session: Session, delivery: ReminderDelivery, *, now: datetime, unknown: bool
) -> None:
    notification = session.scalars(
        select(Notification).where(Notification.reminder_delivery_id == delivery.id)
    ).one()
    prefix = "[Email outcome unknown] " if unknown else "[Email failed] "
    if not notification.title.startswith(prefix):
        notification.title = f"{prefix}{notification.title}"[:255]
    event_id = uuid.uuid4()
    session.add(
        OutboxEvent(
            id=event_id,
            event_type="notification.created",
            entity_id=notification.id,
            payload={
                "event_id": str(event_id),
                "type": "notification.created",
                "occurred_at": now.isoformat(),
                "entity_id": str(notification.id),
                "notification_id": str(notification.id),
                "version": 1,
                "series_id": None,
            },
        )
    )


def deliver(delivery_id: str, claim_token: str, sender: EmailSender | None = None) -> bool:
    did, token, now = uuid.UUID(delivery_id), uuid.UUID(claim_token), utcnow()
    with sync_session_factory() as session, session.begin():
        email = authorize_delivery(
            session, did, token, now=now, grace_seconds=get_settings().reminder_grace_seconds
        )
    if email is None:
        return False
    error: str | None = None
    unknown = False
    if not _valid_recipient(email.recipient):
        error = "Invalid or missing email recipient"
    else:
        try:
            (sender or smtp_sender()).send(email)
        except Exception as exc:  # noqa: BLE001
            error = f"{type(exc).__name__}: {exc}"[:4000]
            unknown = _ambiguous_smtp_error(exc)
    # Never repeat SMTP: attempt_started is already irreversible. If this update
    # crashes, maintenance classifies it unknown.
    with sync_session_factory() as session, session.begin():
        row = session.scalars(
            select(ReminderDelivery).where(ReminderDelivery.id == did).with_for_update()
        ).one()
        if row.state == DeliveryState.attempt_started:
            finished_at = utcnow()
            row.state = (
                DeliveryState.unknown
                if unknown
                else DeliveryState.failed
                if error
                else DeliveryState.sent
            )
            row.error, row.result_at = error, finished_at
            if error:
                _record_visible_email_failure(session, row, now=finished_at, unknown=unknown)
    return error is None


def classify_unknown(
    session: Session, *, now: datetime, older_than_seconds: int = 60, limit: int = 100
) -> int:
    rows = list(
        session.scalars(
            select(ReminderDelivery)
            .where(
                ReminderDelivery.state == DeliveryState.attempt_started,
                ReminderDelivery.authorized_at < now - timedelta(seconds=older_than_seconds),
            )
            .order_by(ReminderDelivery.authorized_at, ReminderDelivery.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )
    for row in rows:
        row.state, row.result_at = DeliveryState.unknown, now
        row.error = row.error or "Worker outcome was not recorded; SMTP is not retried"
        _record_visible_email_failure(session, row, now=now, unknown=True)
    return len(rows)
