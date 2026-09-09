from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator


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
