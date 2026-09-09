from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiError
from app.api.schemas import NoteResponse, TagResponse
from app.db.models import (
    DeliveryState,
    Note,
    NoteTag,
    RecurrenceSeries,
    ReminderDelivery,
    ReminderRule,
    Tag,
)
from app.domain.common import due_at, utcnow


async def note_response(session: AsyncSession, note: Note) -> NoteResponse:
    tags = (
        (
            await session.execute(
                select(Tag)
                .join(NoteTag, NoteTag.tag_id == Tag.id)
                .where(NoteTag.note_id == note.id)
                .order_by(Tag.name, Tag.id)
            )
        )
        .scalars()
        .all()
    )
    offsets = (
        (
            await session.execute(
                select(ReminderRule.offset_minutes)
                .where(ReminderRule.note_id == note.id, ReminderRule.enabled.is_(True))
                .order_by(ReminderRule.offset_minutes)
            )
        )
        .scalars()
        .all()
    )
    return NoteResponse(
        id=note.id,
        title=note.title,
        body=note.body,
        starts_at=note.starts_at,
        active=note.active,
        tags=[TagResponse(id=t.id, name=t.name, color=t.color, version=t.version) for t in tags],
        reminder_offsets_minutes=list(offsets),
        version=note.version,
        created_at=note.created_at,
        updated_at=note.updated_at,
        deleted_at=note.deleted_at,
        series_id=note.series_id,
        recurrence_key=note.recurrence_key,
    )


async def require_note(session: AsyncSession, note_id: uuid.UUID, *, lock: bool = False) -> Note:
    stmt = select(Note).where(Note.id == note_id)
    if lock:
        stmt = stmt.with_for_update()
    note = (await session.execute(stmt)).scalar_one_or_none()
    if note is None:
        raise ApiError(404, "not_found", "Note not found")
    return note


async def check_note_version(session: AsyncSession, note: Note, expected: int) -> None:
    if note.version != expected:
        current = (await note_response(session, note)).model_dump(mode="json")
        raise ApiError(409, "version_conflict", "The note changed", current=current)


async def validate_tags(session: AsyncSession, tag_ids: list[uuid.UUID]) -> None:
    if not tag_ids:
        return
    found = set((await session.execute(select(Tag.id).where(Tag.id.in_(tag_ids)))).scalars())
    missing = [str(item) for item in tag_ids if item not in found]
    if missing:
        raise ApiError(
            422,
            "invalid_tag",
            "One or more tags no longer exist",
            field_errors={"tag_ids": f"unknown tags: {', '.join(missing)}"},
        )


async def replace_tags(session: AsyncSession, note: Note, tag_ids: list[uuid.UUID]) -> None:
    await validate_tags(session, tag_ids)
    existing = set(
        (await session.execute(select(NoteTag.tag_id).where(NoteTag.note_id == note.id))).scalars()
    )
    desired = set(tag_ids)
    await session.execute(
        delete(NoteTag).where(NoteTag.note_id == note.id, NoteTag.tag_id.in_(existing - desired))
    )
    session.add_all(NoteTag(note_id=note.id, tag_id=tag_id) for tag_id in desired - existing)


async def _new_delivery(
    session: AsyncSession, note: Note, rule: ReminderRule, now: datetime
) -> None:
    deadline = due_at(note.starts_at, rule.offset_minutes)
    if not note.active or note.deleted_at is not None:
        state = DeliveryState.cancelled
    elif deadline <= now:
        state = DeliveryState.missed
    else:
        state = DeliveryState.pending
    session.add(
        ReminderDelivery(
            reminder_rule_id=rule.id,
            cycle_number=rule.current_cycle_number,
            due_at=deadline,
            state=state,
        )
    )


async def reconcile_reminders(
    session: AsyncSession,
    note: Note,
    offsets: list[int],
    *,
    schedule_changed: bool,
    now: datetime,
    future_only: bool = False,
) -> None:
    rules = list(
        (
            await session.execute(
                select(ReminderRule)
                .where(ReminderRule.note_id == note.id)
                .order_by(ReminderRule.id)
                .with_for_update()
            )
        ).scalars()
    )
    by_offset = {rule.offset_minutes: rule for rule in rules}
    wanted = set(offsets)
    for rule in rules:
        current = (
            await session.execute(
                select(ReminderDelivery)
                .where(
                    ReminderDelivery.reminder_rule_id == rule.id,
                    ReminderDelivery.cycle_number == rule.current_cycle_number,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if rule.offset_minutes not in wanted:
            rule.enabled = False
            if current is not None and current.state in {
                DeliveryState.pending,
                DeliveryState.claimed,
            }:
                current.state = DeliveryState.cancelled
            continue
        rule.enabled = True
        if schedule_changed:
            if current is not None and current.state in {
                DeliveryState.pending,
                DeliveryState.claimed,
            }:
                current.state = DeliveryState.cancelled
            rule.current_cycle_number += 1
            await session.flush()
            await _new_delivery(session, note, rule, now)
        elif current is not None and current.state in {
            DeliveryState.pending,
            DeliveryState.claimed,
            DeliveryState.cancelled,
        }:
            deadline = due_at(note.starts_at, rule.offset_minutes)
            if note.active and note.deleted_at is None and deadline > now:
                current.state = DeliveryState.pending
                current.claim_token = None
                current.claim_expires_at = None
            elif current.state in {DeliveryState.pending, DeliveryState.claimed}:
                current.state = DeliveryState.cancelled
    for offset in sorted(wanted - by_offset.keys()):
        rule = ReminderRule(
            note_id=note.id, offset_minutes=offset, enabled=True, current_cycle_number=1
        )
        session.add(rule)
        await session.flush()
        await _new_delivery(session, note, rule, now)


async def lock_series(
    session: AsyncSession, note: Note, expected_series_version: int | None
) -> RecurrenceSeries | None:
    if note.series_id is None:
        return None
    if expected_series_version is None:
        raise ApiError(
            422,
            "validation_error",
            "Recurring note mutation requires expected_series_version",
            field_errors={"expected_series_version": "required"},
        )
    series = (
        await session.execute(
            select(RecurrenceSeries).where(RecurrenceSeries.id == note.series_id).with_for_update()
        )
    ).scalar_one()
    if series.version != expected_series_version:
        raise ApiError(
            409,
            "version_conflict",
            "The recurrence series changed",
            current={"id": str(series.id), "version": series.version},
        )
    series.updated_at = utcnow()
    return series
