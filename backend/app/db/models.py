from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import Any, ClassVar

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON

json_type = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class VersionMixin:
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")


class DeliveryState(str, enum.Enum):
    pending = "pending"
    claimed = "claimed"
    attempt_started = "attempt_started"
    sent = "sent"
    failed = "failed"
    unknown = "unknown"
    missed = "missed"
    cancelled = "cancelled"


class UserSettings(Base, TimestampMixin, VersionMixin):
    __tablename__ = "user_settings"
    __mapper_args__: ClassVar[dict[str, Any]] = {"version_id_col": VersionMixin.version}
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)


class Tag(Base, TimestampMixin, VersionMixin):
    __tablename__ = "tags"
    __mapper_args__: ClassVar[dict[str, Any]] = {"version_id_col": VersionMixin.version}
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    color: Mapped[str] = mapped_column(String(7), nullable=False)


class RecurrenceSeries(Base, TimestampMixin, VersionMixin):
    __tablename__ = "recurrence_series"
    __mapper_args__: ClassVar[dict[str, Any]] = {"version_id_col": VersionMixin.version}
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    lineage_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    predecessor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("recurrence_series.id"))
    local_start: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    rrule: Mapped[str] = mapped_column(Text, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    split_boundary: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    template_title: Mapped[str] = mapped_column(String(255), nullable=False)
    template_body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    template_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Note(Base, TimestampMixin, VersionMixin):
    __tablename__ = "notes"
    __mapper_args__: ClassVar[dict[str, Any]] = {"version_id_col": VersionMixin.version}
    __table_args__ = (
        UniqueConstraint("series_id", "recurrence_key", name="uq_note_series_recurrence_key"),
        Index("ix_notes_starts_id", "starts_at", "id"),
        Index("ix_notes_updated_id", "updated_at", "id"),
        Index("ix_notes_state_starts", "deleted_at", "active", "starts_at"),
        Index("ix_notes_deleted_at", "deleted_at"),
        Index(
            "ix_notes_search_trgm",
            "search_text",
            postgresql_using="gin",
            postgresql_ops={"search_text": "gin_trgm_ops"},
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    search_text: Mapped[str] = mapped_column(
        Text, Computed("lower(title || ' ' || body)", persisted=True)
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    series_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("recurrence_series.id"))
    recurrence_key: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NoteTag(Base):
    __tablename__ = "note_tags"
    __table_args__ = (Index("ix_note_tags_tag_note", "tag_id", "note_id"),)
    note_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )


class SeriesTag(Base):
    __tablename__ = "series_tags"
    series_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recurrence_series.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )


class OccurrenceException(Base, TimestampMixin):
    __tablename__ = "occurrence_exceptions"
    __table_args__ = (
        UniqueConstraint("series_id", "recurrence_key", name="uq_exception_series_key"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    series_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("recurrence_series.id"), nullable=False)
    recurrence_key: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    overridden_fields: Mapped[dict[str, Any]] = mapped_column(
        json_type, nullable=False, default=dict
    )
    cancelled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ReminderRule(Base, TimestampMixin):
    __tablename__ = "reminder_rules"
    __table_args__ = (
        UniqueConstraint("note_id", "offset_minutes", name="uq_reminder_note_offset"),
        CheckConstraint("offset_minutes IN (10, 60, 1440)", name="ck_reminder_offset_preset"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    note_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notes.id", ondelete="CASCADE"), nullable=False
    )
    offset_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    current_cycle_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class SeriesReminderTemplate(Base):
    __tablename__ = "series_reminder_templates"
    __table_args__ = (
        CheckConstraint(
            "offset_minutes IN (10, 60, 1440)", name="ck_series_reminder_offset_preset"
        ),
    )
    series_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recurrence_series.id", ondelete="CASCADE"), primary_key=True
    )
    offset_minutes: Mapped[int] = mapped_column(Integer, primary_key=True)


class ReminderDelivery(Base, TimestampMixin):
    __tablename__ = "reminder_deliveries"
    __table_args__ = (
        UniqueConstraint("reminder_rule_id", "cycle_number", name="uq_delivery_rule_cycle"),
        Index("ix_delivery_pending_due", "state", "due_at"),
        Index("ix_delivery_claim_expiry", "claim_expires_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    reminder_rule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reminder_rules.id"), nullable=False
    )
    cycle_number: Mapped[int] = mapped_column(Integer, nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state: Mapped[DeliveryState] = mapped_column(
        Enum(DeliveryState, name="delivery_state"), nullable=False
    )
    claim_token: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    authorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recipient_snapshot: Mapped[str | None] = mapped_column(String(320))
    content_snapshot: Mapped[dict[str, Any] | None] = mapped_column(json_type)
    result_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("reminder_delivery_id", name="uq_notification_delivery"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    reminder_delivery_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reminder_deliveries.id"), nullable=False
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (Index("ix_outbox_unpublished", "published_at", "created_at"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    payload: Mapped[dict[str, Any]] = mapped_column(json_type, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
