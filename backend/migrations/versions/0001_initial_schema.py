"""Initial application schema, frozen as explicit Alembic operations.

Revision ID: 0001
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column(
            "payload",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_outbox_unpublished", "outbox_events", ["published_at", "created_at"], unique=False
    )
    op.create_table(
        "recurrence_series",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lineage_id", sa.Uuid(), nullable=False),
        sa.Column("predecessor_id", sa.Uuid(), nullable=True),
        sa.Column("local_start", sa.DateTime(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("rrule", sa.Text(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("split_boundary", sa.DateTime(timezone=True), nullable=True),
        sa.Column("template_title", sa.String(length=255), nullable=False),
        sa.Column("template_body", sa.Text(), nullable=False),
        sa.Column("template_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(
            ["predecessor_id"],
            ["recurrence_series.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_recurrence_series_lineage_id"), "recurrence_series", ["lineage_id"], unique=False
    )
    op.create_table(
        "tags",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("normalized_name", sa.String(length=100), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_name"),
    )
    op.create_table(
        "user_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "notes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "search_text",
            sa.Text(),
            sa.Computed("lower(title || ' ' || body)", persisted=True),
            nullable=False,
        ),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("series_id", sa.Uuid(), nullable=True),
        sa.Column("recurrence_key", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(
            ["series_id"],
            ["recurrence_series.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("series_id", "recurrence_key", name="uq_note_series_recurrence_key"),
    )
    op.create_index("ix_notes_deleted_at", "notes", ["deleted_at"], unique=False)
    op.create_index(
        "ix_notes_search_trgm",
        "notes",
        ["search_text"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"search_text": "gin_trgm_ops"},
    )
    op.create_index("ix_notes_starts_id", "notes", ["starts_at", "id"], unique=False)
    op.create_index(
        "ix_notes_state_starts", "notes", ["deleted_at", "active", "starts_at"], unique=False
    )
    op.create_index("ix_notes_updated_id", "notes", ["updated_at", "id"], unique=False)
    op.create_table(
        "occurrence_exceptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("series_id", sa.Uuid(), nullable=False),
        sa.Column("recurrence_key", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "overridden_fields",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("cancelled", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["series_id"],
            ["recurrence_series.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("series_id", "recurrence_key", name="uq_exception_series_key"),
    )
    op.create_table(
        "series_reminder_templates",
        sa.Column("series_id", sa.Uuid(), nullable=False),
        sa.Column("offset_minutes", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "offset_minutes IN (10, 60, 1440)", name="ck_series_reminder_offset_preset"
        ),
        sa.ForeignKeyConstraint(["series_id"], ["recurrence_series.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("series_id", "offset_minutes"),
    )
    op.create_table(
        "series_tags",
        sa.Column("series_id", sa.Uuid(), nullable=False),
        sa.Column("tag_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["series_id"], ["recurrence_series.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("series_id", "tag_id"),
    )
    op.create_table(
        "note_tags",
        sa.Column("note_id", sa.Uuid(), nullable=False),
        sa.Column("tag_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["note_id"], ["notes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("note_id", "tag_id"),
    )
    op.create_index("ix_note_tags_tag_note", "note_tags", ["tag_id", "note_id"], unique=False)
    op.create_table(
        "reminder_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("note_id", sa.Uuid(), nullable=False),
        sa.Column("offset_minutes", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("current_cycle_number", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("offset_minutes IN (10, 60, 1440)", name="ck_reminder_offset_preset"),
        sa.ForeignKeyConstraint(["note_id"], ["notes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("note_id", "offset_minutes", name="uq_reminder_note_offset"),
    )
    op.create_table(
        "reminder_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("reminder_rule_id", sa.Uuid(), nullable=False),
        sa.Column("cycle_number", sa.Integer(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "state",
            sa.Enum(
                "pending",
                "claimed",
                "attempt_started",
                "sent",
                "failed",
                "unknown",
                "missed",
                "cancelled",
                name="delivery_state",
            ),
            nullable=False,
        ),
        sa.Column("claim_token", sa.Uuid(), nullable=True),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recipient_snapshot", sa.String(length=320), nullable=True),
        sa.Column(
            "content_snapshot",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("result_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["reminder_rule_id"],
            ["reminder_rules.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reminder_rule_id", "cycle_number", name="uq_delivery_rule_cycle"),
    )
    op.create_index(
        "ix_delivery_claim_expiry", "reminder_deliveries", ["claim_expires_at"], unique=False
    )
    op.create_index(
        "ix_delivery_pending_due", "reminder_deliveries", ["state", "due_at"], unique=False
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("reminder_delivery_id", sa.Uuid(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["reminder_delivery_id"],
            ["reminder_deliveries.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reminder_delivery_id", name="uq_notification_delivery"),
    )


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_index("ix_delivery_pending_due", table_name="reminder_deliveries")
    op.drop_index("ix_delivery_claim_expiry", table_name="reminder_deliveries")
    op.drop_table("reminder_deliveries")
    op.drop_table("reminder_rules")
    op.drop_index("ix_note_tags_tag_note", table_name="note_tags")
    op.drop_table("note_tags")
    op.drop_table("series_tags")
    op.drop_table("series_reminder_templates")
    op.drop_table("occurrence_exceptions")
    op.drop_index("ix_notes_updated_id", table_name="notes")
    op.drop_index("ix_notes_state_starts", table_name="notes")
    op.drop_index("ix_notes_starts_id", table_name="notes")
    op.drop_index(
        "ix_notes_search_trgm",
        table_name="notes",
        postgresql_using="gin",
        postgresql_ops={"search_text": "gin_trgm_ops"},
    )
    op.drop_index("ix_notes_deleted_at", table_name="notes")
    op.drop_table("notes")
    op.drop_table("user_settings")
    op.drop_table("tags")
    op.drop_index(op.f("ix_recurrence_series_lineage_id"), table_name="recurrence_series")
    op.drop_table("recurrence_series")
    op.drop_index("ix_outbox_unpublished", table_name="outbox_events")
    op.drop_table("outbox_events")

    op.execute("DROP TYPE IF EXISTS delivery_state")
