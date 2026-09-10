from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import delete, exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiError
from app.api.schemas import (
    NoteCreate,
    NoteResponse,
    NoteUpdate,
    NotificationResponse,
    Page,
    RecurrencePreviewRequest,
    RecurrencePreviewResponse,
    RestoreRequest,
    SeriesCreate,
    SeriesPortionRequest,
    SeriesResponse,
    SeriesSplit,
    SettingsResponse,
    SettingsUpdate,
    TagCreate,
    TagResponse,
    TagUpdate,
    TrashActionRestoreRequest,
    TrashGroupPage,
    TrashLegacyOccurrence,
    TrashNote,
    TrashSeriesAction,
    UpcomingResponse,
)
from app.config import Settings, get_settings
from app.db.models import (
    Note,
    NoteTag,
    Notification,
    OccurrenceException,
    RecurrenceSeries,
    RecurringTrashAction,
    RecurringTrashActionMember,
    ReminderRule,
    SeriesReminderTemplate,
    SeriesTag,
    Tag,
    UserSettings,
)
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
    validate_tags,
)
from app.domain.recurrence import (
    create_series_rows,
    expand_occurrences,
    normalized_rrule,
    series_response_data,
    set_exception,
)

router = APIRouter(prefix="/api/v1")
SessionDep = Annotated[AsyncSession, Depends(get_async_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
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
        series_ids = list(
            (
                await session.execute(select(SeriesTag.series_id).where(SeriesTag.tag_id == tag.id))
            ).scalars()
        )
        series_rows = list(
            (
                await session.execute(
                    select(RecurrenceSeries)
                    .where(RecurrenceSeries.id.in_(series_ids))
                    .order_by(RecurrenceSeries.id)
                    .with_for_update()
                )
            ).scalars()
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
        await session.execute(delete(SeriesTag).where(SeriesTag.tag_id == tag.id))
        now = utcnow()
        for series in series_rows:
            series.updated_at = now
        for note in notes:
            note.updated_at = now
        event_id, version = tag.id, tag.version
        await session.delete(tag)
        await session.flush()
        for series in series_rows:
            add_event(session, "series.updated", series.id, series.version, series_id=series.id)
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
        await set_exception(session, note)
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
            await set_exception(session, note, cancelled=True)
            await session.flush()
            add_event(session, "note.deleted", note.id, note.version, series_id=note.series_id)
    return Response(status_code=204)


def select_reminder_offsets(note_id: uuid.UUID):

    return select(ReminderRule.offset_minutes).where(
        ReminderRule.note_id == note_id, ReminderRule.enabled.is_(True)
    )


@router.post("/notes/{note_id}/restore", response_model=NoteResponse)
async def restore_note(
    note_id: uuid.UUID, payload: RestoreRequest, session: SessionDep
) -> NoteResponse:
    async with session.begin():
        candidate = await require_note(session, note_id)
        if candidate.current_recurring_trash_action_id is not None:
            if payload.expected_series_version is None:
                raise ApiError(
                    422,
                    "validation_error",
                    "Recurring note restore requires expected_series_version",
                    field_errors={"expected_series_version": "required"},
                )
            await _restore_trash_action(
                session,
                candidate.current_recurring_trash_action_id,
                payload.expected_series_version,
                selected_note_id=note_id,
                expected_note_version=payload.expected_version,
            )
            note = await require_note(session, note_id, lock=True)
            await session.flush()
            return await note_response(session, note)
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
        await set_exception(session, note, cancelled=False)
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
    conditions = [
        Note.superseded_at.is_(None),
        Note.purged_at.is_(None),
        (Note.deleted_at.is_not(None) & Note.purged_at.is_(None))
        if trash
        else Note.deleted_at.is_(None),
    ]
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
                    Note.superseded_at.is_(None),
                    Note.purged_at.is_(None),
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
    base = [
        Note.deleted_at.is_(None),
        Note.superseded_at.is_(None),
        Note.purged_at.is_(None),
        Note.active.is_(True),
    ]
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


@router.get("/trash/groups", response_model=TrashGroupPage)
async def list_trash_groups(
    session: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> TrashGroupPage:
    member_history = select(RecurringTrashActionMember.note_id).where(
        RecurringTrashActionMember.note_id == Note.id
    )
    actions = list(
        (
            await session.execute(
                select(RecurringTrashAction)
                .where(
                    RecurringTrashAction.sealed_at.is_not(None),
                    exists(
                        select(RecurringTrashActionMember.note_id)
                        .join(Note, Note.id == RecurringTrashActionMember.note_id)
                        .where(
                            RecurringTrashActionMember.action_id == RecurringTrashAction.id,
                            Note.current_recurring_trash_action_id == RecurringTrashAction.id,
                        )
                    ),
                )
                .order_by(RecurringTrashAction.id)
            )
        ).scalars()
    )
    legacy = list(
        (
            await session.execute(
                select(Note).where(
                    Note.series_id.is_not(None),
                    Note.deleted_at.is_not(None),
                    Note.series_trashed_at.is_not(None),
                    Note.superseded_at.is_(None),
                    Note.purged_at.is_(None),
                    ~exists(member_history),
                )
            )
        ).scalars()
    )
    ordinary = list(
        (
            await session.execute(
                select(Note).where(
                    Note.deleted_at.is_not(None),
                    Note.superseded_at.is_(None),
                    Note.purged_at.is_(None),
                    Note.current_recurring_trash_action_id.is_(None),
                    or_(
                        Note.series_id.is_(None),
                        Note.series_trashed_at.is_(None),
                        exists(member_history),
                    ),
                )
            )
        ).scalars()
    )
    rows: list[tuple[datetime, int, str, object]] = []
    rows.extend((action.trashed_at, 0, str(action.id), action) for action in actions)
    rows.extend((note.deleted_at, 1, str(note.id), note) for note in legacy)
    rows.extend((note.deleted_at, 2, str(note.id), note) for note in ordinary)
    rows.sort(key=lambda item: (-item[0].timestamp(), item[1], item[2]))
    total = len(rows)
    selected_rows = rows[(page - 1) * page_size : page * page_size]
    items = []
    for _, kind_rank, _, row in selected_rows:
        if kind_rank == 0:
            action = row
            members = list(
                (
                    await session.execute(
                        select(Note)
                        .join(
                            RecurringTrashActionMember,
                            RecurringTrashActionMember.note_id == Note.id,
                        )
                        .where(RecurringTrashActionMember.action_id == action.id)
                        .order_by(Note.recurrence_key, Note.id)
                    )
                ).scalars()
            )
            items.append(
                TrashSeriesAction(
                    action_id=action.id,
                    series_id=action.series_id,
                    boundary_recurrence_key=action.boundary_recurrence_key,
                    trashed_at=action.trashed_at,
                    count=len(members),
                    preview=await note_response(session, members[0]),
                )
            )
        elif kind_rank == 1:
            note = row
            items.append(
                TrashLegacyOccurrence(
                    note=await note_response(session, note), trashed_at=note.deleted_at
                )
            )
        else:
            note = row
            items.append(
                TrashNote(note=await note_response(session, note), trashed_at=note.deleted_at)
            )
    return TrashGroupPage(items=items, total=total, page=page, page_size=page_size)


async def _locked_series(
    session: AsyncSession, series_id: uuid.UUID, expected: int | None = None
) -> RecurrenceSeries:
    row = (
        await session.execute(
            select(RecurrenceSeries)
            .where(RecurrenceSeries.id == series_id, RecurrenceSeries.purged_at.is_(None))
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        raise ApiError(404, "not_found", "Recurrence series not found")
    if expected is not None and row.version != expected:
        raise ApiError(
            409,
            "version_conflict",
            "The recurrence series changed",
            current={"id": str(row.id), "version": row.version},
        )
    return row


@router.post("/series", response_model=SeriesResponse, status_code=status.HTTP_201_CREATED)
async def create_series(
    payload: SeriesCreate, session: SessionDep, settings: SettingsDep
) -> SeriesResponse:
    async with session.begin():
        series = await create_series_rows(
            session, payload, utcnow(), limit=settings.max_series_occurrences
        )
        await session.flush()
        add_event(session, "series.updated", series.id, series.version, series_id=series.id)
        await session.flush()
        return SeriesResponse.model_validate(await series_response_data(session, series))


@router.get("/series/{series_id}", response_model=SeriesResponse)
async def get_series(series_id: uuid.UUID, session: SessionDep) -> SeriesResponse:
    series = (
        await session.execute(
            select(RecurrenceSeries).where(
                RecurrenceSeries.id == series_id, RecurrenceSeries.purged_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if series is None:
        raise ApiError(404, "not_found", "Recurrence series not found")
    return SeriesResponse.model_validate(await series_response_data(session, series))


@router.post("/series/{series_id}/split", response_model=SeriesResponse)
async def split_series(
    series_id: uuid.UUID, payload: SeriesSplit, session: SessionDep, settings: SettingsDep
) -> SeriesResponse:
    async with session.begin():
        # The predecessor row is always the first lock in a split. This serializes
        # competing splits without reversing the established series -> notes order.
        old = await _locked_series(session, series_id)
        successor_id = (
            await session.execute(
                select(RecurrenceSeries.id)
                .where(RecurrenceSeries.predecessor_id == old.id)
                .order_by(RecurrenceSeries.id)
                .limit(1)
            )
        ).scalar_one_or_none()
        if old.split_boundary is not None or successor_id is not None:
            raise ApiError(
                409,
                "series_not_leaf",
                "Only the open leaf recurrence series can be split",
                current={
                    "id": str(old.id),
                    "split_boundary": (
                        old.split_boundary.isoformat() if old.split_boundary is not None else None
                    ),
                    "successor_id": str(successor_id) if successor_id is not None else None,
                },
            )
        if old.version != payload.series_version:
            raise ApiError(
                409,
                "version_conflict",
                "The recurrence series changed",
                current={"id": str(old.id), "version": old.version},
            )
        selected = (
            await session.execute(
                select(Note)
                .where(
                    Note.series_id == old.id,
                    Note.recurrence_key == payload.recurrence_key,
                    Note.superseded_at.is_(None),
                    Note.purged_at.is_(None),
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if selected is None:
            raise ApiError(404, "occurrence_not_found", "Selected occurrence not found")
        if selected.version != payload.expected_occurrence_version:
            raise ApiError(
                409,
                "version_conflict",
                "The selected occurrence changed",
                current={"id": str(selected.id), "version": selected.version},
            )
        affected = list(
            (
                await session.execute(
                    select(Note)
                    .where(
                        Note.series_id == old.id,
                        Note.recurrence_key >= selected.recurrence_key,
                        Note.superseded_at.is_(None),
                    )
                    .order_by(Note.id)
                    .with_for_update()
                )
            ).scalars()
        )
        if any(
            note.current_recurring_trash_action_id is not None
            or note.series_trashed_at is not None
            for note in affected
        ):
            raise ApiError(
                409,
                "trash_action_overlap",
                "Restore the affected Trash entries before splitting the series",
            )
        now = utcnow()
        historical = [note for note in affected if note.starts_at <= now]
        if historical:
            raise ApiError(
                409,
                "historical_replacement",
                "A future-series change cannot rewrite an occurrence that has already started",
                current={"note_ids": [str(x.id) for x in historical]},
            )
        try:
            generated = expand_occurrences(
                payload.local_start,
                payload.timezone,
                payload.frequency,
                payload.end_date,
                limit=min(settings.max_series_occurrences, 10_000),
            )
        except (ValueError, OverflowError) as exc:
            raise ApiError(
                422, "invalid_recurrence", "Invalid recurrence", field_errors={"end_date": str(exc)}
            ) from exc
        if not generated:
            raise ApiError(422, "invalid_recurrence", "Series has no valid occurrences")
        if payload.starts_at.astimezone(UTC) != generated[0].instant:
            raise ApiError(
                422,
                "invalid_recurrence",
                "starts_at conflicts with local_start",
                field_errors={"starts_at": "must equal the first valid recurrence instant"},
            )
        historical_instants = [
            occurrence.instant for occurrence in generated if occurrence.instant <= now
        ]
        if historical_instants:
            raise ApiError(
                409,
                "historical_replacement",
                "A future-series change cannot create an occurrence that has already started",
                current={
                    "recurrence_keys": [instant.isoformat() for instant in historical_instants]
                },
            )
        generated_keys = {occurrence.instant for occurrence in generated}
        colliding_notes = list(
            (
                await session.execute(
                    select(Note.id, Note.recurrence_key, Note.starts_at)
                    .join(RecurrenceSeries, RecurrenceSeries.id == Note.series_id)
                    .where(
                        RecurrenceSeries.lineage_id == old.lineage_id,
                        Note.recurrence_key < selected.recurrence_key,
                        or_(
                            Note.recurrence_key.in_(generated_keys),
                            Note.starts_at.in_(generated_keys),
                        ),
                        Note.superseded_at.is_(None),
                    )
                    .order_by(Note.recurrence_key, Note.id)
                )
            ).all()
        )
        if colliding_notes:
            raise ApiError(
                409,
                "recurrence_collision",
                "The replacement schedule collides with an earlier occurrence",
                current={
                    "note_ids": [str(note_id) for note_id, _, _ in colliding_notes],
                    "recurrence_keys": [key.isoformat() for _, key, _ in colliding_notes],
                    "starts_at": [instant.isoformat() for _, _, instant in colliding_notes],
                },
            )
        await validate_tags(session, payload.tag_ids)
        title = payload.title.strip()
        if not title:
            raise ApiError(
                422, "validation_error", "Invalid note", field_errors={"title": "must not be blank"}
            )
        successor = RecurrenceSeries(
            lineage_id=old.lineage_id,
            predecessor_id=old.id,
            local_start=payload.local_start,
            timezone=payload.timezone,
            rrule=normalized_rrule(payload.frequency),
            end_date=payload.end_date,
            template_title=title,
            template_body=payload.body,
            template_active=payload.active,
        )
        session.add(successor)
        await session.flush()
        session.add_all(SeriesTag(series_id=successor.id, tag_id=x) for x in payload.tag_ids)
        session.add_all(
            SeriesReminderTemplate(series_id=successor.id, offset_minutes=x)
            for x in payload.reminder_offsets_minutes
        )
        boundary_local = selected.recurrence_key.astimezone(ZoneInfo(old.timezone))
        old.end_date = boundary_local.date() - timedelta(days=1)
        old.split_boundary = selected.recurrence_key
        old.updated_at = now
        # Purged rows are permanent technical tombstones. Never revive one as the
        # successor occurrence; create a new row and supersede the tombstone below.
        by_key = {note.recurrence_key: note for note in affected if note.purged_at is None}
        kept: set[uuid.UUID] = set()
        for occurrence in generated:
            note = by_key.get(occurrence.instant)
            if note is None:
                note = Note(
                    title=title,
                    body=payload.body,
                    starts_at=occurrence.instant,
                    active=payload.active,
                    series_id=successor.id,
                    recurrence_key=occurrence.instant,
                )
                session.add(note)
                await session.flush()
                schedule_changed = False
            else:
                kept.add(note.id)
                schedule_changed = note.starts_at != occurrence.instant
                note.series_id = successor.id
                note.title, note.body, note.starts_at, note.active = (
                    title,
                    payload.body,
                    occurrence.instant,
                    payload.active,
                )
                note.deleted_at = note.series_trashed_at = note.superseded_at = None
                note.updated_at = now
                await session.execute(delete(NoteTag).where(NoteTag.note_id == note.id))
            session.add_all(NoteTag(note_id=note.id, tag_id=x) for x in payload.tag_ids)
            await reconcile_reminders(
                session,
                note,
                payload.reminder_offsets_minutes,
                schedule_changed=schedule_changed,
                now=now,
            )
        for note in affected:
            if note.id not in kept:
                if note.purged_at is not None:
                    continue
                note.deleted_at = now
                note.superseded_at = now
                note.updated_at = now
                offsets = list((await session.execute(select_reminder_offsets(note.id))).scalars())
                await reconcile_reminders(session, note, offsets, schedule_changed=False, now=now)
        purged_keys = {note.recurrence_key for note in affected if note.purged_at is not None}
        exception_delete = delete(OccurrenceException).where(
            OccurrenceException.series_id == old.id,
            OccurrenceException.recurrence_key >= selected.recurrence_key,
        )
        if purged_keys:
            # Keep the minimal cancellation marker that makes a purged recurring
            # deletion auditable. Other future overrides belong to the old portion.
            exception_delete = exception_delete.where(
                OccurrenceException.recurrence_key.not_in(purged_keys)
            )
        await session.execute(exception_delete)
        await session.flush()
        add_event(
            session, "series.updated", successor.id, successor.version, series_id=successor.id
        )
        await session.flush()
        return SeriesResponse.model_validate(await series_response_data(session, successor))


async def _portion_boundary(
    session: AsyncSession,
    series: RecurrenceSeries,
    requested: datetime | None,
    *,
    restoring: bool = False,
) -> datetime:
    conditions = [Note.series_id == series.id, Note.superseded_at.is_(None)]
    if restoring:
        conditions.append(Note.series_trashed_at.is_not(None))
    stmt = select(func.min(Note.recurrence_key)).where(*conditions)
    boundary = requested or (await session.execute(stmt)).scalar_one_or_none()
    if boundary is None:
        raise ApiError(
            409,
            "nothing_to_restore" if restoring else "empty_series",
            "The series portion is empty",
        )
    existence_conditions = [
        Note.series_id == series.id,
        Note.recurrence_key == boundary,
        Note.superseded_at.is_(None),
    ]
    if restoring:
        existence_conditions.append(Note.series_trashed_at.is_not(None))
    exists = (
        await session.execute(select(Note.id).where(*existence_conditions))
    ).scalar_one_or_none()
    if exists is None:
        raise ApiError(404, "occurrence_not_found", "Selected occurrence not found")
    return boundary


@router.post("/series/{series_id}/trash", status_code=status.HTTP_204_NO_CONTENT)
async def trash_series_portion(
    series_id: uuid.UUID, payload: SeriesPortionRequest, session: SessionDep
) -> Response:
    async with session.begin():
        series = await _locked_series(session, series_id, payload.series_version)
        boundary = await _portion_boundary(session, series, payload.recurrence_key)
        candidate_ids = list(
            (
                await session.execute(
                    select(Note.id).where(
                        Note.series_id == series.id,
                        Note.recurrence_key >= boundary,
                        Note.deleted_at.is_(None),
                        Note.superseded_at.is_(None),
                        Note.purged_at.is_(None),
                    )
                )
            ).scalars()
        )
        if not candidate_ids:
            raise ApiError(409, "empty_series", "The series portion is empty")
        action = RecurringTrashAction(
            series_id=series.id, boundary_recurrence_key=boundary
        )
        session.add(action)
        await session.flush()
        notes = list(
            (
                await session.execute(
                    select(Note)
                    .where(
                        Note.id.in_(candidate_ids),
                        Note.deleted_at.is_(None),
                        Note.superseded_at.is_(None),
                        Note.purged_at.is_(None),
                    )
                    .order_by(Note.id)
                    .with_for_update()
                )
            ).scalars()
        )
        if len(notes) != len(candidate_ids):
            raise ApiError(409, "version_conflict", "The series portion changed")
        session.add_all(
            RecurringTrashActionMember(action_id=action.id, note_id=note.id) for note in notes
        )
        await session.flush()
        now = action.trashed_at
        for note in notes:
            note.deleted_at = now
            note.current_recurring_trash_action_id = action.id
            note.updated_at = now
            offsets = list((await session.execute(select_reminder_offsets(note.id))).scalars())
            await reconcile_reminders(session, note, offsets, schedule_changed=False, now=now)
        series.updated_at = now
        await session.flush()
        await session.execute(
            update(RecurringTrashAction)
            .where(RecurringTrashAction.id == action.id)
            .values(sealed_at=func.clock_timestamp())
        )
        add_event(session, "series.updated", series.id, series.version, series_id=series.id)
    return Response(status_code=204)


async def _restore_trash_action(
    session: AsyncSession,
    action_id: uuid.UUID,
    expected_series_version: int,
    *,
    selected_note_id: uuid.UUID | None = None,
    expected_note_version: int | None = None,
) -> RecurrenceSeries:
    identity = (
        await session.execute(
            select(RecurringTrashAction.series_id).where(RecurringTrashAction.id == action_id)
        )
    ).scalar_one_or_none()
    if identity is None:
        raise ApiError(404, "trash_action_not_found", "Trash action not found")
    series = await _locked_series(session, identity, expected_series_version)
    action = (
        await session.execute(
            select(RecurringTrashAction)
            .where(RecurringTrashAction.id == action_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    member_ids = list(
        (
            await session.execute(
                select(RecurringTrashActionMember.note_id)
                .where(RecurringTrashActionMember.action_id == action.id)
                .order_by(RecurringTrashActionMember.note_id)
            )
        ).scalars()
    )
    notes = list(
        (
            await session.execute(
                select(Note).where(Note.id.in_(member_ids)).order_by(Note.id).with_for_update()
            )
        ).scalars()
    )
    await session.execute(
        select(RecurringTrashActionMember)
        .where(RecurringTrashActionMember.action_id == action.id)
        .order_by(RecurringTrashActionMember.note_id)
        .with_for_update()
    )
    current = [note for note in notes if note.current_recurring_trash_action_id == action.id]
    if not current:
        raise ApiError(409, "nothing_to_restore", "Trash action is already closed")
    if len(current) != len(notes):
        raise ApiError(409, "trash_invariant_breach", "Trash action membership is incomplete")
    if selected_note_id is not None:
        selected_note = next((note for note in notes if note.id == selected_note_id), None)
        if selected_note is None:
            raise ApiError(404, "not_found", "Note not found")
        await check_note_version(session, selected_note, expected_note_version)  # type: ignore[arg-type]
    now = utcnow()
    if action.trashed_at <= now - timedelta(days=30):
        raise ApiError(410, "retention_expired", "The trash action can no longer be restored")
    for note in notes:
        note.current_recurring_trash_action_id = None
        note.deleted_at = None
        note.updated_at = now
        offsets = list((await session.execute(select_reminder_offsets(note.id))).scalars())
        await reconcile_reminders(
            session, note, offsets, schedule_changed=False, now=now, future_only=True
        )
    series.updated_at = now
    await session.flush()
    add_event(session, "series.updated", series.id, series.version, series_id=series.id)
    return series


@router.post("/trash/actions/{action_id}/restore", response_model=SeriesResponse)
async def restore_trash_action(
    action_id: uuid.UUID, payload: TrashActionRestoreRequest, session: SessionDep
) -> SeriesResponse:
    async with session.begin():
        series = await _restore_trash_action(
            session, action_id, payload.expected_series_version
        )
        await session.flush()
        return SeriesResponse.model_validate(await series_response_data(session, series))


@router.post("/series/preview", response_model=RecurrencePreviewResponse)
async def preview_series(
    payload: RecurrencePreviewRequest, settings: SettingsDep
) -> RecurrencePreviewResponse:
    try:
        occurrences = expand_occurrences(
            payload.local_start,
            payload.timezone,
            payload.frequency,
            payload.end_date,
            limit=min(settings.max_series_occurrences, 10_000),
        )
    except (ValueError, OverflowError) as exc:
        raise ApiError(422, "invalid_recurrence", "Invalid recurrence") from exc
    if not occurrences:
        raise ApiError(422, "invalid_recurrence", "Series has no valid occurrences")
    return RecurrencePreviewResponse(
        starts_at=occurrences[0].instant, occurrence_count=len(occurrences)
    )


@router.post("/series/{series_id}/restore", response_model=SeriesResponse)
async def restore_series_portion(
    series_id: uuid.UUID, payload: SeriesPortionRequest, session: SessionDep
) -> SeriesResponse:
    async with session.begin():
        series = await _locked_series(session, series_id, payload.series_version)
        action_conditions = [
            Note.series_id == series.id,
            Note.current_recurring_trash_action_id.is_not(None),
        ]
        legacy_conditions = [
            Note.series_id == series.id,
            Note.series_trashed_at.is_not(None),
            Note.current_recurring_trash_action_id.is_(None),
            Note.deleted_at.is_not(None),
            Note.superseded_at.is_(None),
            Note.purged_at.is_(None),
        ]
        if payload.recurrence_key is not None:
            action_conditions.append(Note.recurrence_key >= payload.recurrence_key)
            legacy_conditions.append(Note.recurrence_key >= payload.recurrence_key)
        action_ids = list(
            (
                await session.execute(
                    select(Note.current_recurring_trash_action_id)
                    .where(*action_conditions)
                    .distinct()
                    .order_by(Note.current_recurring_trash_action_id)
                )
            ).scalars()
        )
        has_legacy = (await session.execute(select(Note.id).where(*legacy_conditions).limit(1))).first()
        if action_ids:
            if len(action_ids) != 1 or has_legacy is not None:
                raise ApiError(
                    409,
                    "individual_restore_required",
                    "Restore each trash action individually.",
                )
            action_boundary = (
                await session.execute(
                    select(RecurringTrashAction.boundary_recurrence_key).where(
                        RecurringTrashAction.id == action_ids[0]
                    )
                )
            ).scalar_one()
            if payload.recurrence_key is not None and payload.recurrence_key != action_boundary:
                raise ApiError(
                    409,
                    "individual_restore_required",
                    "Restore each trash action individually.",
                )
            series = await _restore_trash_action(session, action_ids[0], payload.series_version)
            await session.flush()
            return SeriesResponse.model_validate(await series_response_data(session, series))
        boundary = await _portion_boundary(session, series, payload.recurrence_key, restoring=True)
        notes = list(
            (
                await session.execute(
                    select(Note)
                    .where(
                        Note.series_id == series.id,
                        Note.recurrence_key >= boundary,
                        Note.series_trashed_at.is_not(None),
                        Note.superseded_at.is_(None),
                    )
                    .order_by(Note.id)
                    .with_for_update()
                )
            ).scalars()
        )
        now = utcnow()
        expired = [n for n in notes if n.series_trashed_at <= now - timedelta(days=30)]
        if expired:
            raise ApiError(410, "retention_expired", "The series portion can no longer be restored")
        for note in notes:
            exception = (
                await session.execute(
                    select(OccurrenceException).where(
                        OccurrenceException.series_id == series.id,
                        OccurrenceException.recurrence_key == note.recurrence_key,
                    )
                )
            ).scalar_one_or_none()
            note.series_trashed_at = None
            if exception is None or not exception.cancelled:
                note.deleted_at = None
                note.updated_at = now
                offsets = list((await session.execute(select_reminder_offsets(note.id))).scalars())
                await reconcile_reminders(
                    session, note, offsets, schedule_changed=False, now=now, future_only=True
                )
        series.updated_at = now
        await session.flush()
        add_event(session, "series.updated", series.id, series.version, series_id=series.id)
        await session.flush()
        return SeriesResponse.model_validate(await series_response_data(session, series))
