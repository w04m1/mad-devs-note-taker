from __future__ import annotations

import calendar
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil import tz
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiError
from app.db.models import (
    Note,
    NoteTag,
    OccurrenceException,
    RecurrenceSeries,
    ReminderRule,
    SeriesReminderTemplate,
    SeriesTag,
)
from app.domain.notes import reconcile_reminders, validate_tags

Frequency = Literal["daily", "weekly", "monthly"]
MAX_OCCURRENCES = 10_000


@dataclass(frozen=True)
class Occurrence:
    local: datetime
    instant: datetime


def normalized_rrule(frequency: Frequency) -> str:
    return f"FREQ={frequency.upper()};INTERVAL=1"


def frequency_from_rrule(value: str) -> Frequency:
    first = value.split(";", 1)[0]
    result = first.removeprefix("FREQ=").lower()
    if result not in {"daily", "weekly", "monthly"}:
        raise ValueError(f"unsupported stored RRULE: {value}")
    return result  # type: ignore[return-value]


def _next_month(value: datetime, wanted_day: int) -> datetime:
    year, month = value.year, value.month + 1
    if month == 13:
        year, month = year + 1, 1
    # Keep the wanted DTSTART day. Use day 1 as an iteration cursor when absent.
    day = wanted_day if wanted_day <= calendar.monthrange(year, month)[1] else 1
    return value.replace(year=year, month=month, day=day)


def expand_occurrences(
    local_start: datetime,
    timezone: str,
    frequency: Frequency,
    end_date: date,
    *,
    limit: int = MAX_OCCURRENCES,
) -> list[Occurrence]:
    """Expand a finite wall-clock series. End date is inclusive.

    Nonexistent wall times are skipped. Ambiguous wall times use fold=0, the
    earlier instant. Invalid monthly dates are skipped, never clamped.
    """
    if local_start.tzinfo is not None and local_start.utcoffset() is not None:
        raise ValueError("local_start must be naive")
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("unknown IANA timezone") from None
    zone = tz.gettz(timezone)
    if zone is None:
        raise ValueError("unknown IANA timezone")
    if end_date < local_start.date():
        raise ValueError("end_date must be on or after local_start")
    result: list[Occurrence] = []
    cursor = local_start
    wanted_day = local_start.day
    while cursor.date() <= end_date:
        valid_calendar_day = frequency != "monthly" or cursor.day == wanted_day
        if valid_calendar_day:
            candidate = cursor.replace(tzinfo=zone, fold=0)
            if tz.datetime_exists(candidate):
                # fold=0 is dateutil's earlier instant for an overlap.
                result.append(Occurrence(cursor, candidate.astimezone(UTC)))
                if len(result) > limit:
                    raise OverflowError(f"series exceeds {limit} occurrences")
        if frequency == "daily":
            cursor += timedelta(days=1)
        elif frequency == "weekly":
            cursor += timedelta(days=7)
        else:
            cursor = _next_month(cursor, wanted_day)
    return result


async def series_response_data(session: AsyncSession, series: RecurrenceSeries) -> dict:
    tags = list(
        (
            await session.execute(select(SeriesTag.tag_id).where(SeriesTag.series_id == series.id))
        ).scalars()
    )
    offsets = list(
        (
            await session.execute(
                select(SeriesReminderTemplate.offset_minutes)
                .where(SeriesReminderTemplate.series_id == series.id)
                .order_by(SeriesReminderTemplate.offset_minutes)
            )
        ).scalars()
    )
    count = (
        await session.execute(
            select(func.count())
            .select_from(Note)
            .where(Note.series_id == series.id, Note.superseded_at.is_(None))
        )
    ).scalar_one()
    return {
        "id": series.id,
        "lineage_id": series.lineage_id,
        "predecessor_id": series.predecessor_id,
        "local_start": series.local_start,
        "timezone": series.timezone,
        "frequency": frequency_from_rrule(series.rrule),
        "end_date": series.end_date,
        "split_boundary": series.split_boundary,
        "title": series.template_title,
        "body": series.template_body,
        "active": series.template_active,
        "tag_ids": tags,
        "reminder_offsets_minutes": offsets,
        "version": series.version,
        "created_at": series.created_at,
        "updated_at": series.updated_at,
        "occurrence_count": count,
    }


async def materialize_note(
    session: AsyncSession,
    series: RecurrenceSeries,
    occurrence: Occurrence,
    *,
    title: str,
    body: str,
    active: bool,
    tag_ids: list[uuid.UUID],
    offsets: list[int],
    now: datetime,
    note: Note | None = None,
) -> Note:
    if note is None:
        note = Note(
            title=title,
            body=body,
            starts_at=occurrence.instant,
            active=active,
            series_id=series.id,
            recurrence_key=occurrence.instant,
        )
        session.add(note)
        await session.flush()
    else:
        schedule_changed = note.starts_at != occurrence.instant
        note.series_id = series.id
        note.recurrence_key = occurrence.instant
        note.title, note.body, note.starts_at, note.active = title, body, occurrence.instant, active
        note.deleted_at = None
        note.superseded_at = None
        await session.flush()
        await session.execute(delete(NoteTag).where(NoteTag.note_id == note.id))
        await reconcile_reminders(
            session, note, offsets, schedule_changed=schedule_changed, now=now
        )
    session.add_all(NoteTag(note_id=note.id, tag_id=tag_id) for tag_id in tag_ids)
    if (
        note is not None
        and not (
            await session.execute(select(ReminderRule.id).where(ReminderRule.note_id == note.id))
        ).first()
    ):
        await reconcile_reminders(session, note, offsets, schedule_changed=False, now=now)
    return note


async def create_series_rows(
    session: AsyncSession, payload, now: datetime, *, limit: int = MAX_OCCURRENCES
) -> RecurrenceSeries:
    await validate_tags(session, payload.tag_ids)
    try:
        occurrences = expand_occurrences(
            payload.local_start, payload.timezone, payload.frequency, payload.end_date, limit=limit
        )
    except (ValueError, OverflowError) as exc:
        field = "end_date" if "end_date" in str(exc) or "exceeds" in str(exc) else "timezone"
        raise ApiError(
            422, "invalid_recurrence", "Invalid recurrence", field_errors={field: str(exc)}
        ) from exc
    if not occurrences:
        raise ApiError(
            422,
            "invalid_recurrence",
            "Series has no valid occurrences",
            field_errors={"local_start": "all local occurrences are nonexistent"},
        )
    if payload.starts_at.astimezone(UTC) != occurrences[0].instant:
        raise ApiError(
            422,
            "invalid_recurrence",
            "starts_at conflicts with local_start",
            field_errors={"starts_at": "must equal the first valid recurrence instant"},
        )
    title = payload.title.strip()
    if not title:
        raise ApiError(
            422, "validation_error", "Invalid note", field_errors={"title": "must not be blank"}
        )
    series_id = uuid.uuid4()
    series = RecurrenceSeries(
        id=series_id,
        lineage_id=series_id,
        local_start=payload.local_start,
        timezone=payload.timezone,
        rrule=normalized_rrule(payload.frequency),
        end_date=payload.end_date,
        template_title=title,
        template_body=payload.body,
        template_active=payload.active,
    )
    session.add(series)
    session.add_all(SeriesTag(series_id=series.id, tag_id=x) for x in payload.tag_ids)
    session.add_all(
        SeriesReminderTemplate(series_id=series.id, offset_minutes=x)
        for x in payload.reminder_offsets_minutes
    )
    await session.flush()
    for occurrence in occurrences:
        note = Note(
            title=title,
            body=payload.body,
            starts_at=occurrence.instant,
            active=payload.active,
            series_id=series.id,
            recurrence_key=occurrence.instant,
        )
        session.add(note)
        await session.flush()
        session.add_all(NoteTag(note_id=note.id, tag_id=x) for x in payload.tag_ids)
        await reconcile_reminders(
            session, note, payload.reminder_offsets_minutes, schedule_changed=False, now=now
        )
    return series


async def set_exception(
    session: AsyncSession, note: Note, *, cancelled: bool | None = None
) -> None:
    if note.series_id is None or note.recurrence_key is None:
        return
    series = (
        await session.execute(select(RecurrenceSeries).where(RecurrenceSeries.id == note.series_id))
    ).scalar_one()
    row = (
        await session.execute(
            select(OccurrenceException)
            .where(
                OccurrenceException.series_id == note.series_id,
                OccurrenceException.recurrence_key == note.recurrence_key,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        row = OccurrenceException(
            series_id=note.series_id,
            recurrence_key=note.recurrence_key,
            overridden_fields={},
            cancelled=False,
        )
        session.add(row)
    if cancelled is not None:
        row.cancelled = cancelled
    note_tags = sorted(
        str(x)
        for x in (
            await session.execute(select(NoteTag.tag_id).where(NoteTag.note_id == note.id))
        ).scalars()
    )
    series_tags = sorted(
        str(x)
        for x in (
            await session.execute(select(SeriesTag.tag_id).where(SeriesTag.series_id == series.id))
        ).scalars()
    )
    note_offsets = sorted(
        (
            await session.execute(
                select(ReminderRule.offset_minutes).where(
                    ReminderRule.note_id == note.id, ReminderRule.enabled.is_(True)
                )
            )
        ).scalars()
    )
    series_offsets = sorted(
        (
            await session.execute(
                select(SeriesReminderTemplate.offset_minutes).where(
                    SeriesReminderTemplate.series_id == series.id
                )
            )
        ).scalars()
    )
    values = {
        "title": note.title,
        "body": note.body,
        "starts_at": note.starts_at.isoformat(),
        "active": note.active,
        "tag_ids": note_tags,
        "reminder_offsets_minutes": note_offsets,
    }
    defaults = {
        "title": series.template_title,
        "body": series.template_body,
        "starts_at": note.recurrence_key.isoformat(),
        "active": series.template_active,
        "tag_ids": series_tags,
        "reminder_offsets_minutes": series_offsets,
    }
    row.overridden_fields = {key: value for key, value in values.items() if value != defaults[key]}
