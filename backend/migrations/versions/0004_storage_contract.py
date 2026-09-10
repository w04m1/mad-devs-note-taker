"""Install immutable recurring-Trash identity and purge safety contracts.

Revision ID: 0004_storage_contract
Revises: 0003_background
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_storage_contract"
down_revision = "0003_background"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("recurrence_series", sa.Column("purged_at", sa.DateTime(timezone=True)))
    op.create_index("ix_recurrence_series_purged_at", "recurrence_series", ["purged_at"])

    op.create_table(
        "recurring_trash_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("series_id", sa.Uuid(), nullable=False),
        sa.Column("boundary_recurrence_key", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "trashed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("sealed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["series_id"], ["recurrence_series.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_recurring_trash_actions_series_id", "recurring_trash_actions", ["series_id"]
    )
    op.create_table(
        "recurring_trash_action_members",
        sa.Column("action_id", sa.Uuid(), nullable=False),
        sa.Column("note_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["action_id"], ["recurring_trash_actions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["note_id"], ["notes.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("action_id", "note_id"),
    )
    op.add_column("notes", sa.Column("current_recurring_trash_action_id", sa.Uuid()))
    op.create_index(
        "ix_notes_current_recurring_trash_action_id",
        "notes",
        ["current_recurring_trash_action_id"],
    )
    op.create_foreign_key(
        "fk_notes_current_trash_membership",
        "notes",
        "recurring_trash_action_members",
        ["current_recurring_trash_action_id", "id"],
        ["action_id", "note_id"],
        ondelete="NO ACTION",
        deferrable=True,
        initially="DEFERRED",
    )

    op.add_column("reminder_deliveries", sa.Column("error_code", sa.String(64)))
    op.execute(
        """
        UPDATE reminder_deliveries
        SET error_code = CASE
          WHEN state = 'failed' AND error IS NOT NULL THEN 'delivery_failed_legacy'
          WHEN state = 'unknown' AND error IS NOT NULL THEN 'delivery_outcome_unknown_legacy'
          ELSE NULL
        END
        """
    )
    op.drop_column("reminder_deliveries", "error")
    op.execute(
        """
        UPDATE reminder_deliveries SET
          claim_token = NULL, claim_expires_at = NULL, authorized_at = NULL,
          recipient_snapshot = NULL, content_snapshot = NULL, result_at = NULL,
          error_code = NULL
        WHERE state = 'pending';
        UPDATE reminder_deliveries SET
          state = 'pending', claim_token = NULL, claim_expires_at = NULL,
          authorized_at = NULL, recipient_snapshot = NULL, content_snapshot = NULL,
          result_at = NULL, error_code = NULL
        WHERE state = 'claimed' AND (claim_token IS NULL OR claim_expires_at IS NULL);
        UPDATE reminder_deliveries SET
          claim_token = NULL, claim_expires_at = NULL, authorized_at = NULL,
          recipient_snapshot = NULL, content_snapshot = NULL,
          result_at = COALESCE(result_at, updated_at, clock_timestamp()), error_code = NULL
        WHERE state IN ('missed','cancelled');
        UPDATE reminder_deliveries SET error_code = 'delivery_failed_legacy'
        WHERE state = 'failed' AND error_code IS NULL;
        UPDATE reminder_deliveries SET error_code = 'delivery_outcome_unknown_legacy'
        WHERE state = 'unknown' AND error_code IS NULL;
        """
    )
    op.create_check_constraint(
        "ck_delivery_error_code_allowlist",
        "reminder_deliveries",
        "error_code IS NULL OR error_code IN ("
        "'invalid_recipient','smtp_send_failed','smtp_outcome_unknown',"
        "'worker_outcome_unknown','delivery_failed_legacy',"
        "'delivery_outcome_unknown_legacy')",
    )
    op.create_check_constraint(
        "ck_delivery_state_shape",
        "reminder_deliveries",
        """
        (state = 'pending' AND claim_token IS NULL AND claim_expires_at IS NULL
          AND authorized_at IS NULL AND recipient_snapshot IS NULL
          AND content_snapshot IS NULL AND result_at IS NULL AND error_code IS NULL)
        OR
        (state = 'claimed' AND claim_token IS NOT NULL AND claim_expires_at IS NOT NULL
          AND authorized_at IS NULL AND recipient_snapshot IS NULL
          AND content_snapshot IS NULL AND result_at IS NULL AND error_code IS NULL)
        OR
        (state = 'attempt_started' AND claim_token IS NOT NULL AND claim_expires_at IS NULL
          AND authorized_at IS NOT NULL AND recipient_snapshot IS NOT NULL
          AND content_snapshot IS NOT NULL AND result_at IS NULL AND error_code IS NULL)
        OR
        (state IN ('sent','failed','unknown') AND claim_token IS NOT NULL
          AND claim_expires_at IS NULL AND authorized_at IS NOT NULL
          AND ((recipient_snapshot IS NOT NULL AND content_snapshot IS NOT NULL)
            OR (recipient_snapshot IS NULL AND content_snapshot IS NULL))
          AND result_at IS NOT NULL
          AND ((state = 'sent' AND error_code IS NULL)
            OR (state IN ('failed','unknown') AND error_code IS NOT NULL)))
        OR
        (state IN ('missed','cancelled') AND claim_token IS NULL
          AND claim_expires_at IS NULL AND authorized_at IS NULL
          AND recipient_snapshot IS NULL AND content_snapshot IS NULL
          AND result_at IS NOT NULL AND error_code IS NULL)
        """,
    )

    op.add_column("outbox_events", sa.Column("error_code", sa.String(64)))
    op.execute(
        """
        UPDATE outbox_events SET error_code = 'outbox_publish_failed_legacy'
        WHERE last_error IS NOT NULL
        """
    )
    op.drop_column("outbox_events", "last_error")
    op.create_check_constraint(
        "ck_outbox_error_code_allowlist",
        "outbox_events",
        "error_code IS NULL OR error_code IN "
        "('outbox_publish_failed','outbox_publish_failed_legacy')",
    )
    op.create_check_constraint(
        "ck_outbox_state_shape",
        "outbox_events",
        """
        (published_at IS NOT NULL AND next_attempt_at IS NULL AND error_code IS NULL)
        OR published_at IS NULL
        """,
    )

    # Repair directly accessible superseded ghosts without changing ordinary deleted notes.
    op.execute(
        """
        UPDATE notes SET deleted_at = superseded_at
        WHERE superseded_at IS NOT NULL AND purged_at IS NULL AND deleted_at IS NULL
        """
    )
    op.execute(
        """
        UPDATE reminder_deliveries AS delivery
        SET state = 'cancelled', claim_token = NULL, claim_expires_at = NULL,
            result_at = clock_timestamp(), error_code = NULL
        FROM reminder_rules AS rule, notes AS note
        WHERE delivery.reminder_rule_id = rule.id
          AND rule.note_id = note.id
          AND (note.superseded_at IS NOT NULL OR note.purged_at IS NOT NULL)
          AND delivery.state IN ('pending','claimed')
        """
    )
    op.execute(
        """
        DELETE FROM occurrence_exceptions AS exception
        USING notes AS note
        WHERE exception.series_id = note.series_id
          AND exception.recurrence_key = note.recurrence_key
          AND note.superseded_at IS NOT NULL AND note.purged_at IS NULL
        """
    )
    op.execute(
        """
        UPDATE occurrence_exceptions AS exception
        SET cancelled = TRUE, overridden_fields = '{}'::jsonb, updated_at = clock_timestamp()
        FROM notes AS note
        WHERE exception.series_id = note.series_id
          AND exception.recurrence_key = note.recurrence_key
          AND note.purged_at IS NOT NULL
        """
    )

    op.execute(
        """
        CREATE FUNCTION nt_guard_trash_action() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'DELETE' AND OLD.sealed_at IS NOT NULL THEN
            RAISE EXCEPTION 'sealed recurring trash actions are immutable';
          END IF;
          IF TG_OP = 'UPDATE' THEN
            IF OLD.sealed_at IS NOT NULL THEN
              RAISE EXCEPTION 'sealed recurring trash actions are immutable';
            END IF;
            IF NEW.id IS DISTINCT FROM OLD.id OR NEW.series_id IS DISTINCT FROM OLD.series_id
               OR NEW.boundary_recurrence_key IS DISTINCT FROM OLD.boundary_recurrence_key
               OR NEW.trashed_at IS DISTINCT FROM OLD.trashed_at THEN
              RAISE EXCEPTION 'recurring trash action identity is immutable';
            END IF;
            IF NEW.sealed_at IS NOT NULL THEN
              IF NOT EXISTS (
                SELECT 1 FROM recurring_trash_action_members WHERE action_id = OLD.id
              ) OR EXISTS (
                SELECT 1 FROM recurring_trash_action_members m
                JOIN notes n ON n.id = m.note_id
                WHERE m.action_id = OLD.id AND (
                  n.series_id IS DISTINCT FROM OLD.series_id
                  OR n.recurrence_key < OLD.boundary_recurrence_key
                  OR n.deleted_at IS DISTINCT FROM OLD.trashed_at
                  OR n.current_recurring_trash_action_id IS DISTINCT FROM OLD.id
                  OR n.purged_at IS NOT NULL OR n.superseded_at IS NOT NULL
                )
              ) OR EXISTS (
                SELECT 1 FROM notes n
                WHERE n.current_recurring_trash_action_id = OLD.id
                  AND NOT EXISTS (
                    SELECT 1 FROM recurring_trash_action_members m
                    WHERE m.action_id = OLD.id AND m.note_id = n.id
                  )
              ) THEN
                RAISE EXCEPTION 'recurring trash action membership is incomplete';
              END IF;
              NEW.sealed_at := clock_timestamp();
            END IF;
          END IF;
          RETURN COALESCE(NEW, OLD);
        END $$;
        CREATE TRIGGER trg_guard_trash_action
          BEFORE UPDATE OR DELETE ON recurring_trash_actions
          FOR EACH ROW EXECUTE FUNCTION nt_guard_trash_action();

        CREATE FUNCTION nt_require_sealed_trash_action() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM recurring_trash_actions
            WHERE id = NEW.id AND sealed_at IS NOT NULL
          ) THEN
            RAISE EXCEPTION 'recurring trash action must be sealed before commit';
          END IF;
          RETURN NULL;
        END $$;
        CREATE CONSTRAINT TRIGGER trg_require_sealed_trash_action
          AFTER INSERT ON recurring_trash_actions DEFERRABLE INITIALLY DEFERRED
          FOR EACH ROW EXECUTE FUNCTION nt_require_sealed_trash_action();

        CREATE FUNCTION nt_guard_trash_member() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE selected_action uuid := COALESCE(NEW.action_id, OLD.action_id);
        BEGIN
          IF EXISTS (
            SELECT 1 FROM recurring_trash_actions
            WHERE id = selected_action AND sealed_at IS NOT NULL
          ) THEN
            RAISE EXCEPTION 'sealed recurring trash action membership is immutable';
          END IF;
          RETURN COALESCE(NEW, OLD);
        END $$;
        CREATE TRIGGER trg_guard_trash_member
          BEFORE INSERT OR UPDATE OR DELETE ON recurring_trash_action_members
          FOR EACH ROW EXECUTE FUNCTION nt_guard_trash_member();

        CREATE FUNCTION nt_guard_note_lifecycle() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'DELETE' AND OLD.purged_at IS NOT NULL THEN
            RAISE EXCEPTION 'purged notes are immutable';
          END IF;
          IF TG_OP = 'UPDATE' THEN
            IF OLD.purged_at IS NOT NULL THEN
              RAISE EXCEPTION 'purged notes are immutable';
            END IF;
            IF NEW.current_recurring_trash_action_id IS DISTINCT FROM
               OLD.current_recurring_trash_action_id
               AND NEW.current_recurring_trash_action_id IS NOT NULL
               AND EXISTS (
                 SELECT 1 FROM recurring_trash_actions
                 WHERE id = NEW.current_recurring_trash_action_id AND sealed_at IS NOT NULL
               ) THEN
              RAISE EXCEPTION 'cannot assign membership after action seal';
            END IF;
          END IF;
          RETURN COALESCE(NEW, OLD);
        END $$;
        CREATE TRIGGER trg_guard_note_lifecycle
          BEFORE UPDATE OR DELETE ON notes
          FOR EACH ROW EXECUTE FUNCTION nt_guard_note_lifecycle();

        CREATE FUNCTION nt_guard_series_lifecycle() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF (TG_OP = 'DELETE' AND OLD.purged_at IS NOT NULL)
             OR (TG_OP = 'UPDATE' AND OLD.purged_at IS NOT NULL) THEN
            RAISE EXCEPTION 'purged recurrence series are immutable';
          END IF;
          RETURN COALESCE(NEW, OLD);
        END $$;
        CREATE TRIGGER trg_guard_series_lifecycle
          BEFORE UPDATE OR DELETE ON recurrence_series
          FOR EACH ROW EXECUTE FUNCTION nt_guard_series_lifecycle();
        """
    )


def downgrade() -> None:
    raise RuntimeError(
        "0004_storage_contract is activation-irreversible; restore the validated pre-cutover backup"
    )
