from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiError
from app.api.schemas import (
    NoteCreate,
    NoteResponse,
    NoteUpdate,
    NotificationResponse,
    Page,
    RestoreRequest,
    SettingsResponse,
    SettingsUpdate,
    TagCreate,
    TagResponse,
    TagUpdate,
    UpcomingResponse,
)
from app.config import get_settings
from app.db.models import Note, NoteTag, Notification, Tag, UserSettings
from app.db.session import get_async_session
from app.domain.common import add_event, utcnow, validate_email, validate_timezone
from app.domain.notes import (
    check_note_version,
    lock_series,
    note_response,
    notes_response,
    reconcile_reminders,
    replace_tags,
    require_note,
)

router = APIRouter(prefix="/api/v1")
SessionDep = Annotated[AsyncSession, Depends(get_async_session)]
_PROFILE_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def _tag_response(tag: Tag) -> TagResponse:
    return TagResponse(id=tag.id, name=tag.name, color=tag.color, version=tag.version)


def _settings_response(settings: UserSettings) -> SettingsResponse:
    return SettingsResponse(
        email=settings.email, timezone=settings.timezone, version=settings.version
    )


def _validate_color(color: str) -> str:
    if not _COLOR.fullmatch(color):
        raise ApiError(
            422, "validation_error", "Invalid tag", field_errors={"color": "must be #RRGGBB"}
        )
    return color.lower()


def _normalize_name(name: str) -> tuple[str, str]:
    display = name.strip()
    if not display:
        raise ApiError(
            422, "validation_error", "Invalid tag", field_errors={"name": "must not be blank"}
        )
    return display, display.casefold()


async def _settings(session: AsyncSession, *, lock: bool = False) -> UserSettings:
    stmt = select(UserSettings).where(UserSettings.id == _PROFILE_ID)
    if lock:
        stmt = stmt.with_for_update()
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        config = get_settings()
        row = UserSettings(
            id=_PROFILE_ID, email=config.app_default_email, timezone=config.app_default_timezone
        )
        session.add(row)
        await session.flush()
    return row


@router.get("/settings", response_model=SettingsResponse)
async def get_profile_settings(session: SessionDep) -> SettingsResponse:
    async with session.begin():
        return _settings_response(await _settings(session))


@router.patch("/settings", response_model=SettingsResponse)
async def update_profile_settings(payload: SettingsUpdate, session: SessionDep) -> SettingsResponse:
    async with session.begin():
        row = await _settings(session, lock=True)
        if row.version != payload.expected_version:
            raise ApiError(
                409,
                "version_conflict",
                "Settings changed",
                current=_settings_response(row).model_dump(mode="json"),
            )
        row.email = validate_email(payload.email.strip())
        row.timezone = validate_timezone(payload.timezone)
        row.updated_at = utcnow()
        await session.flush()
        add_event(session, "settings.updated", row.id, row.version)
        await session.flush()
        return _settings_response(row)


@router.get("/tags", response_model=list[TagResponse])
async def list_tags(session: SessionDep) -> list[TagResponse]:
    rows = (await session.execute(select(Tag).order_by(Tag.name, Tag.id))).scalars()
    return [_tag_response(row) for row in rows]


@router.post("/tags", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
async def create_tag(payload: TagCreate, session: SessionDep) -> TagResponse:
    async with session.begin():
        name, normalized = _normalize_name(payload.name)
        if (
            await session.execute(select(Tag.id).where(Tag.normalized_name == normalized))
        ).scalar_one_or_none():
            raise ApiError(
                409,
                "tag_name_conflict",
                "A tag with this name already exists",
                field_errors={"name": "must be unique"},
            )
        tag = Tag(name=name, normalized_name=normalized, color=_validate_color(payload.color))
        session.add(tag)
        await session.flush()
        add_event(session, "tag.created", tag.id, tag.version)
        await session.flush()
        return _tag_response(tag)


@router.patch("/tags/{tag_id}", response_model=TagResponse)
async def update_tag(tag_id: uuid.UUID, payload: TagUpdate, session: SessionDep) -> TagResponse:
    async with session.begin():
        tag = (
            await session.execute(select(Tag).where(Tag.id == tag_id).with_for_update())
        ).scalar_one_or_none()
        if tag is None:
            raise ApiError(404, "not_found", "Tag not found")
        if tag.version != payload.expected_version:
            raise ApiError(
                409,
                "version_conflict",
                "The tag changed",
                current=_tag_response(tag).model_dump(mode="json"),
            )
        name, normalized = _normalize_name(payload.name)
        duplicate = (
            await session.execute(
                select(Tag.id).where(Tag.normalized_name == normalized, Tag.id != tag.id)
            )
        ).scalar_one_or_none()
        if duplicate:
            raise ApiError(
                409,
                "tag_name_conflict",
                "A tag with this name already exists",
                field_errors={"name": "must be unique"},
            )
        tag.name, tag.normalized_name, tag.color = name, normalized, _validate_color(payload.color)
        tag.updated_at = utcnow()
        await session.flush()
        add_event(session, "tag.updated", tag.id, tag.version)
        await session.flush()
        return _tag_response(tag)


@router.delete("/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(
    tag_id: uuid.UUID, session: SessionDep, expected_version: Annotated[int, Query(ge=1)]
) -> Response:
    async with session.begin():
        tag = (
            await session.execute(select(Tag).where(Tag.id == tag_id).with_for_update())
        ).scalar_one_or_none()
        if tag is None:
            raise ApiError(404, "not_found", "Tag not found")
        if tag.version != expected_version:
            raise ApiError(
                409,
                "version_conflict",
                "The tag changed",
                current=_tag_response(tag).model_dump(mode="json"),
            )
        notes = list(
            (
                await session.execute(
                    select(Note)
                    .join(NoteTag)
                    .where(NoteTag.tag_id == tag.id)
                    .order_by(Note.id)
                    .with_for_update()
                )
            ).scalars()
        )
        await session.execute(delete(NoteTag).where(NoteTag.tag_id == tag.id))
        now = utcnow()
        for note in notes:
            note.updated_at = now
        event_id, version = tag.id, tag.version
        await session.delete(tag)
        add_event(session, "tag.deleted", event_id, version)
    return Response(status_code=204)


@router.post("/notes", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
async def create_note(payload: NoteCreate, session: SessionDep) -> NoteResponse:
    async with session.begin():
        now = utcnow()
        note = Note(
            title=payload.title.strip(),
            body=payload.body,
            starts_at=payload.starts_at,
            active=payload.active,
        )
        if not note.title:
            raise ApiError(
                422, "validation_error", "Invalid note", field_errors={"title": "must not be blank"}
            )
        session.add(note)
        await session.flush()
        await replace_tags(session, note, payload.tag_ids)
        await reconcile_reminders(
            session, note, payload.reminder_offsets_minutes, schedule_changed=False, now=now
        )
        add_event(session, "note.created", note.id, note.version)
        await session.flush()
        return await note_response(session, note)


async def _locked_note_and_series(
    session: AsyncSession, note_id: uuid.UUID, expected_series_version: int | None
) -> Note:
    candidate = await require_note(session, note_id)
    await lock_series(session, candidate, expected_series_version)
    return await require_note(session, note_id, lock=True)


@router.get("/notes/{note_id}", response_model=NoteResponse)
async def get_note(note_id: uuid.UUID, session: SessionDep) -> NoteResponse:
    return await note_response(session, await require_note(session, note_id))


@router.patch("/notes/{note_id}", response_model=NoteResponse)
async def update_note(note_id: uuid.UUID, payload: NoteUpdate, session: SessionDep) -> NoteResponse:
    async with session.begin():
        note = await _locked_note_and_series(session, note_id, payload.expected_series_version)
        await check_note_version(session, note, payload.expected_version)
        if note.deleted_at is not None:
            raise ApiError(
                409,
                "note_deleted",
                "Restore the note before editing",
                current=(await note_response(session, note)).model_dump(mode="json"),
            )
        title = payload.title.strip()
        if not title:
            raise ApiError(
                422, "validation_error", "Invalid note", field_errors={"title": "must not be blank"}
            )
        schedule_changed = note.starts_at != payload.starts_at
        note.title, note.body, note.starts_at, note.active = (
            title,
            payload.body,
            payload.starts_at,
            payload.active,
        )
        note.updated_at = utcnow()
        await replace_tags(session, note, payload.tag_ids)
        await reconcile_reminders(
            session,
            note,
            payload.reminder_offsets_minutes,
            schedule_changed=schedule_changed,
            now=utcnow(),
        )
        await session.flush()
        add_event(session, "note.updated", note.id, note.version, series_id=note.series_id)
        await session.flush()
        return await note_response(session, note)


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    note_id: uuid.UUID,
    session: SessionDep,
    expected_version: Annotated[int, Query(ge=1)],
    expected_series_version: Annotated[int | None, Query(ge=1)] = None,
) -> Response:
    async with session.begin():
        note = await _locked_note_and_series(session, note_id, expected_series_version)
        await check_note_version(session, note, expected_version)
        if note.deleted_at is None:
            note.deleted_at = utcnow()
            note.updated_at = utcnow()
            offsets = list((await session.execute(select_reminder_offsets(note.id))).scalars())
            await reconcile_reminders(session, note, offsets, schedule_changed=False, now=utcnow())
            await session.flush()
            add_event(session, "note.deleted", note.id, note.version, series_id=note.series_id)
    return Response(status_code=204)


def select_reminder_offsets(note_id: uuid.UUID):
    from app.db.models import ReminderRule

    return select(ReminderRule.offset_minutes).where(
        ReminderRule.note_id == note_id, ReminderRule.enabled.is_(True)
    )


@router.post("/notes/{note_id}/restore", response_model=NoteResponse)
async def restore_note(
    note_id: uuid.UUID, payload: RestoreRequest, session: SessionDep
) -> NoteResponse:
    async with session.begin():
        note = await _locked_note_and_series(session, note_id, payload.expected_series_version)
        await check_note_version(session, note, payload.expected_version)
        if note.deleted_at is None:
            raise ApiError(
                409,
                "note_not_deleted",
                "Note is not in trash",
                current=(await note_response(session, note)).model_dump(mode="json"),
            )
        if note.deleted_at <= utcnow() - timedelta(days=30):
            raise ApiError(410, "retention_expired", "The note can no longer be restored")
        note.deleted_at = None
        note.updated_at = utcnow()
        offsets = list((await session.execute(select_reminder_offsets(note.id))).scalars())
        await reconcile_reminders(
            session, note, offsets, schedule_changed=False, now=utcnow(), future_only=True
        )
        await session.flush()
        add_event(session, "note.restored", note.id, note.version, series_id=note.series_id)
        await session.flush()
        return await note_response(session, note)


def _aware_query(value: datetime | None, field: str) -> datetime | None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ApiError(
            422,
            "validation_error",
            "Invalid datetime",
            field_errors={field: "must include a UTC offset"},
        )
    return value


def _notes_filter(
    *,
    q: str | None,
    tag_ids: list[uuid.UUID],
    active: bool | None,
    starts_from: datetime | None,
    starts_to: datetime | None,
    trash: bool,
):
    conditions = [Note.deleted_at.is_not(None) if trash else Note.deleted_at.is_(None)]
    if active is not None:
        conditions.append(Note.active.is_(active))
    if starts_from is not None:
        conditions.append(Note.starts_at >= starts_from)
    if starts_to is not None:
        conditions.append(Note.starts_at < starts_to)
    if q is not None:
        cleaned = q.strip()
        if len(cleaned) < 3:
            raise ApiError(
                422,
                "validation_error",
                "Search text is too short",
                field_errors={"q": "enter at least 3 non-whitespace characters"},
            )
        escaped = cleaned.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append(Note.search_text.ilike(f"%{escaped}%", escape="\\"))
    if tag_ids:
        unique_ids = set(tag_ids)
        matching = (
            select(NoteTag.note_id)
            .where(NoteTag.tag_id.in_(unique_ids))
            .group_by(NoteTag.note_id)
            .having(func.count(func.distinct(NoteTag.tag_id)) == len(unique_ids))
        )
        conditions.append(Note.id.in_(matching))
    return conditions


@router.get("/notes", response_model=Page)
async def list_notes(
    session: SessionDep,
    q: str | None = None,
    tag_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    active: bool | None = None,
    starts_from: datetime | None = None,
    starts_to: datetime | None = None,
    trash: bool = False,
    sort: Literal["starts_at", "updated_at"] = "starts_at",
    direction: Literal["asc", "desc"] = "asc",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> Page:
    starts_from, starts_to = (
        _aware_query(starts_from, "starts_from"),
        _aware_query(starts_to, "starts_to"),
    )
    if starts_from and starts_to and starts_from >= starts_to:
        raise ApiError(
            422,
            "validation_error",
            "Invalid range",
            field_errors={"starts_to": "must be after starts_from"},
        )
    conditions = _notes_filter(
        q=q,
        tag_ids=tag_id or [],
        active=active,
        starts_from=starts_from,
        starts_to=starts_to,
        trash=trash,
    )
    total = (
        await session.execute(select(func.count()).select_from(Note).where(*conditions))
    ).scalar_one()
    order_column = Note.starts_at if sort == "starts_at" else Note.updated_at
    order = order_column.asc() if direction == "asc" else order_column.desc()
    id_order = Note.id.asc() if direction == "asc" else Note.id.desc()
    rows = list(
        (
            await session.execute(
                select(Note)
                .where(*conditions)
                .order_by(order, id_order)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars()
    )
    return Page(
        items=[item.model_dump(mode="json") for item in await notes_response(session, rows)],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/calendar", response_model=list[NoteResponse])
async def calendar(
    session: SessionDep,
    starts_from: datetime,
    starts_to: datetime,
) -> list[NoteResponse]:
    starts_from, starts_to = (
        _aware_query(starts_from, "starts_from"),
        _aware_query(starts_to, "starts_to"),
    )
    assert starts_from is not None and starts_to is not None
    if starts_to <= starts_from or starts_to - starts_from > timedelta(days=93):
        raise ApiError(
            422,
            "invalid_range",
            "Calendar range must be positive and no longer than 93 days",
            field_errors={"starts_to": "narrow the range"},
        )
    rows = list(
        (
            await session.execute(
                select(Note)
                .where(
                    Note.deleted_at.is_(None),
                    Note.starts_at >= starts_from,
                    Note.starts_at < starts_to,
                )
                .order_by(Note.starts_at, Note.id)
                .limit(5001)
            )
        ).scalars()
    )
    if len(rows) > 5000:
        raise ApiError(413, "range_too_large", "Too many calendar notes; narrow the range")
    return await notes_response(session, rows)


async def _note_group(session: AsyncSession, conditions: list, page: int, page_size: int) -> Page:
    total = (
        await session.execute(select(func.count()).select_from(Note).where(*conditions))
    ).scalar_one()
    rows = list(
        (
            await session.execute(
                select(Note)
                .where(*conditions)
                .order_by(Note.starts_at, Note.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars()
    )
    return Page(
        items=[item.model_dump(mode="json") for item in await notes_response(session, rows)],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/upcoming", response_model=UpcomingResponse)
async def upcoming(
    session: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> UpcomingResponse:
    profile = await _settings(session)
    now = utcnow()
    local_now = now.astimezone(ZoneInfo(profile.timezone))
    tomorrow_local = datetime.combine(
        local_now.date() + timedelta(days=1), datetime.min.time(), ZoneInfo(profile.timezone)
    )
    week_end_local = datetime.combine(
        local_now.date() + timedelta(days=7 - local_now.weekday()),
        datetime.min.time(),
        ZoneInfo(profile.timezone),
    )
    tomorrow, week_end = tomorrow_local.astimezone(UTC), week_end_local.astimezone(UTC)
    base = [Note.deleted_at.is_(None), Note.active.is_(True)]
    today = await _note_group(
        session, base + [Note.starts_at >= now, Note.starts_at < tomorrow], page, page_size
    )
    week = await _note_group(
        session, base + [Note.starts_at >= tomorrow, Note.starts_at < week_end], page, page_size
    )
    past = await _note_group(session, base + [Note.starts_at < now], page, page_size)
    next_note = (
        await session.execute(select(func.min(Note.starts_at)).where(*base, Note.starts_at >= now))
    ).scalar_one()
    candidates = [tomorrow, week_end]
    if next_note is not None:
        candidates.append(next_note)
    return UpcomingResponse(
        today=today, week=week, past=past, server_now=now, next_transition_at=min(candidates)
    )


@router.get("/notifications", response_model=Page)
async def notifications(
    session: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> Page:
    total = (await session.execute(select(func.count()).select_from(Notification))).scalar_one()
    rows = list(
        (
            await session.execute(
                select(Notification)
                .order_by(Notification.created_at.desc(), Notification.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars()
    )
    items = [
        NotificationResponse.model_validate(row, from_attributes=True).model_dump(mode="json")
        for row in rows
    ]
    return Page(items=items, total=total, page=page, page_size=page_size)
