from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.db.models import Base, DeliveryState, Note, ReminderDelivery, ReminderRule


def test_all_planned_entities_are_registered() -> None:
    assert set(Base.metadata.tables) == {
        "user_settings",
        "notes",
        "tags",
        "note_tags",
        "recurrence_series",
        "series_tags",
        "occurrence_exceptions",
        "reminder_rules",
        "series_reminder_templates",
        "reminder_deliveries",
        "notifications",
        "outbox_events",
    }


def test_note_uses_timezone_aware_instants_and_concurrency_version() -> None:
    assert Note.__table__.c.starts_at.type.timezone is True
    assert Note.__mapper__.version_id_col is Note.__table__.c.version
    assert {"series_id", "recurrence_key"} in [
        {column.name for column in constraint.columns}
        for constraint in Note.__table__.constraints
        if hasattr(constraint, "columns")
    ]


def test_reminder_contract_is_encoded_in_schema() -> None:
    ddl = str(CreateTable(ReminderRule.__table__).compile(dialect=postgresql.dialect()))
    assert "offset_minutes IN (10, 60, 1440)" in ddl
    assert {item.value for item in DeliveryState} == {
        "pending",
        "claimed",
        "attempt_started",
        "sent",
        "failed",
        "unknown",
        "missed",
        "cancelled",
    }
    uniques = [
        {column.name for column in constraint.columns}
        for constraint in ReminderDelivery.__table__.constraints
        if hasattr(constraint, "columns")
    ]
    assert {"reminder_rule_id", "cycle_number"} in uniques
