"""Add recurrence lifecycle markers.

Revision ID: 0002_recurrence
Revises: 0001
"""

from alembic import op

revision = "0002_recurrence"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE notes ADD COLUMN IF NOT EXISTS superseded_at TIMESTAMPTZ")
    op.execute("ALTER TABLE notes ADD COLUMN IF NOT EXISTS series_trashed_at TIMESTAMPTZ")
    op.execute("CREATE INDEX IF NOT EXISTS ix_notes_superseded_at ON notes (superseded_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_notes_series_trashed_at ON notes (series_trashed_at)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_notes_series_trashed_at")
    op.execute("DROP INDEX IF EXISTS ix_notes_superseded_at")
    op.execute("ALTER TABLE notes DROP COLUMN IF EXISTS series_trashed_at")
    op.execute("ALTER TABLE notes DROP COLUMN IF EXISTS superseded_at")
