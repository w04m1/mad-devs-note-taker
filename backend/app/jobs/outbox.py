from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from redis import Redis
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import OutboxEvent
from app.db.session import sync_session_factory

CHANNEL = "notetaker.events"


def utcnow() -> datetime:
    return datetime.now(UTC)


def publish_batch(session: Session, publish, *, now: datetime, limit: int = 100) -> int:
    rows = list(
        session.scalars(
            select(OutboxEvent)
            .where(
                OutboxEvent.published_at.is_(None),
                or_(OutboxEvent.next_attempt_at.is_(None), OutboxEvent.next_attempt_at <= now),
            )
            .order_by(OutboxEvent.created_at, OutboxEvent.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )
    published = 0
    for row in rows:
        row.attempts += 1
        try:
            publish(CHANNEL, json.dumps(row.payload, separators=(",", ":")))
        except Exception:  # noqa: BLE001
            row.error_code = "outbox_publish_failed"
            row.next_attempt_at = now + timedelta(seconds=min(60, 2 ** min(row.attempts - 1, 6)))
        else:
            row.published_at, row.next_attempt_at, row.error_code = now, None, None
            published += 1
    return published


def publish_outbox() -> int:
    client = Redis.from_url(
        get_settings().redis_url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2
    )
    try:
        with sync_session_factory() as session, session.begin():
            return publish_batch(session, client.publish, now=utcnow())
    finally:
        client.close()
