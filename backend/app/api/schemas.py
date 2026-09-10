from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include a UTC offset")
    return value


class ErrorResponse(BaseModel):
    code: str
    message: str
    field_errors: dict[str, str] | None = None
    current: dict | None = None


class TagResponse(BaseModel):
    id: uuid.UUID
    name: str
    color: str
    version: int


class TagCreate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=100)]
    color: str


class TagUpdate(TagCreate):
    expected_version: int = Field(ge=1)


class SettingsResponse(BaseModel):
    email: str
    timezone: str
    version: int


class SettingsUpdate(BaseModel):
    email: str
    timezone: str
    expected_version: int = Field(ge=1)


class NoteFields(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=255)]
    body: str = ""
    starts_at: datetime
    active: bool = True
    tag_ids: list[uuid.UUID] = Field(default_factory=list)
    reminder_offsets_minutes: list[Literal[10, 60, 1440]] = Field(default_factory=list)

    @field_validator("starts_at")
    @classmethod
    def aware_starts_at(cls, value: datetime) -> datetime:
        return _aware(value)

    @field_validator("tag_ids", "reminder_offsets_minutes")
    @classmethod
    def distinct_values(cls, value: list) -> list:
        if len(value) != len(set(value)):
            raise ValueError("values must be distinct")
        return value


class NoteCreate(NoteFields):
    pass


class NoteUpdate(NoteFields):
    expected_version: int = Field(ge=1)
    expected_series_version: int | None = Field(default=None, ge=1)


class RestoreRequest(BaseModel):
    expected_version: int = Field(ge=1)
    expected_series_version: int | None = Field(default=None, ge=1)


class NoteResponse(BaseModel):
    id: uuid.UUID
    title: str
    body: str
    starts_at: datetime
    active: bool
    tags: list[TagResponse]
    reminder_offsets_minutes: list[int]
    version: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    series_id: uuid.UUID | None
    recurrence_key: datetime | None


class Page(BaseModel):
    items: list
    total: int
    page: int
    page_size: int


class TrashSeriesAction(BaseModel):
    kind: Literal["series_action"] = "series_action"
    action_id: uuid.UUID
    series_id: uuid.UUID
    boundary_recurrence_key: datetime
    trashed_at: datetime
    count: int
    preview: NoteResponse


class TrashLegacyOccurrence(BaseModel):
    kind: Literal["legacy_occurrence"] = "legacy_occurrence"
    note: NoteResponse
    trashed_at: datetime


class TrashNote(BaseModel):
    kind: Literal["note"] = "note"
    note: NoteResponse
    trashed_at: datetime


TrashGroup = Annotated[
    TrashSeriesAction | TrashLegacyOccurrence | TrashNote, Field(discriminator="kind")
]


class TrashGroupPage(BaseModel):
    items: list[TrashGroup]
    total: int
    page: int
    page_size: int


class TrashActionRestoreRequest(BaseModel):
    expected_series_version: int = Field(ge=1)


RecurrenceFrequency = Literal["daily", "weekly", "monthly"]


def _local(value: datetime) -> datetime:
    if value.tzinfo is not None and value.utcoffset() is not None:
        raise ValueError("datetime must be a local value without a UTC offset")
    return value


class SeriesFields(NoteFields):
    local_start: datetime
    timezone: Annotated[str, Field(min_length=1, max_length=64)]
    frequency: RecurrenceFrequency
    end_date: date

    @field_validator("local_start")
    @classmethod
    def naive_local_start(cls, value: datetime) -> datetime:
        return _local(value)


class SeriesCreate(SeriesFields):
    @model_validator(mode="after")
    def matching_first_instant(self):
        # starts_at is retained for the shared NoteWrite contract. Recurrence is
        # authoritative from local_start + timezone and checked by the service.
        return self


class SeriesSplit(SeriesFields):
    recurrence_key: datetime
    expected_series_version: int | None = Field(default=None, ge=1)
    expected_version: int | None = Field(default=None, ge=1, deprecated=True)
    expected_occurrence_version: int = Field(ge=1)

    @field_validator("recurrence_key")
    @classmethod
    def aware_key(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def resolve_series_version(self):
        canonical = self.__dict__.get("expected_series_version")
        legacy = self.__dict__.get("expected_version")
        if canonical is None and legacy is None:
            raise ValueError("expected_series_version is required")
        if canonical is not None and legacy is not None and canonical != legacy:
            raise ValueError("series version aliases must match")
        return self

    @property
    def series_version(self) -> int:
        return self.__dict__.get("expected_series_version") or self.__dict__["expected_version"]


class RecurrencePreviewRequest(BaseModel):
    local_start: datetime
    timezone: Annotated[str, Field(min_length=1, max_length=64)]
    frequency: RecurrenceFrequency
    end_date: date

    @field_validator("local_start")
    @classmethod
    def naive_local_start(cls, value: datetime) -> datetime:
        return _local(value)


class RecurrencePreviewResponse(BaseModel):
    starts_at: datetime
    occurrence_count: int


class SeriesPortionRequest(BaseModel):
    expected_series_version: int | None = Field(default=None, ge=1)
    expected_version: int | None = Field(default=None, ge=1, deprecated=True)
    recurrence_key: datetime | None = None

    @field_validator("recurrence_key")
    @classmethod
    def aware_key(cls, value: datetime | None) -> datetime | None:
        return _aware(value) if value is not None else None

    @model_validator(mode="after")
    def resolve_series_version(self):
        canonical = self.__dict__.get("expected_series_version")
        legacy = self.__dict__.get("expected_version")
        if canonical is None and legacy is None:
            raise ValueError("expected_series_version is required")
        if canonical is not None and legacy is not None and canonical != legacy:
            raise ValueError("series version aliases must match")
        return self

    @property
    def series_version(self) -> int:
        return self.__dict__.get("expected_series_version") or self.__dict__["expected_version"]


class SeriesResponse(BaseModel):
    id: uuid.UUID
    lineage_id: uuid.UUID
    predecessor_id: uuid.UUID | None
    local_start: datetime
    timezone: str
    frequency: RecurrenceFrequency
    end_date: date
    split_boundary: datetime | None
    title: str
    body: str
    active: bool
    tag_ids: list[uuid.UUID]
    reminder_offsets_minutes: list[int]
    version: int
    created_at: datetime
    updated_at: datetime
    occurrence_count: int


class NotificationResponse(BaseModel):
    id: uuid.UUID
    reminder_delivery_id: uuid.UUID
    scheduled_at: datetime
    created_at: datetime
    title: str
    body: str


class UpcomingResponse(BaseModel):
    today: Page
    week: Page
    past: Page
    server_now: datetime
    next_transition_at: datetime | None
