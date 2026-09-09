from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiError
from app.db.models import OutboxEvent

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def utcnow() -> datetime:
    return datetime.now(UTC)


def validate_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ApiError(
            422,
            "validation_error",
            "Invalid settings",
            field_errors={"timezone": "must be a valid IANA timezone"},
        ) from None
    return value


def validate_email(value: str) -> str:
    if len(value) > 320 or not _EMAIL.fullmatch(value):
        raise ApiError(
            422,
            "validation_error",
            "Invalid settings",
            field_errors={"email": "must be a valid email address"},
        )
    return value


def add_event(
    session: AsyncSession,
    event_type: str,
    entity_id: uuid.UUID,
    version: int,
    *,
    series_id: uuid.UUID | None = None,
) -> None:
    event_id = uuid.uuid4()
    session.add(
        OutboxEvent(
            id=event_id,
            event_type=event_type,
            entity_id=entity_id,
            payload={
                "event_id": str(event_id),
                "type": event_type,
                "occurred_at": utcnow().isoformat(),
                "entity_id": str(entity_id),
                "version": version,
                "series_id": str(series_id) if series_id else None,
            },
        )
    )


def due_at(starts_at: datetime, offset_minutes: int) -> datetime:
    return starts_at - timedelta(minutes=offset_minutes)
