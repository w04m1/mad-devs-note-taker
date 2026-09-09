"""Hide redacted retained note records after trash expiry.

Revision ID: 0003_background
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0003_background"
down_revision = "0002_recurrence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if "purged_at" not in {column["name"] for column in inspector.get_columns("notes")}:
        op.add_column("notes", sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True))
    if "ix_notes_purged_at" not in {index["name"] for index in inspector.get_indexes("notes")}:
        op.create_index("ix_notes_purged_at", "notes", ["purged_at"])


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if "ix_notes_purged_at" in {index["name"] for index in inspector.get_indexes("notes")}:
        op.drop_index("ix_notes_purged_at", table_name="notes")
    if "purged_at" in {column["name"] for column in inspector.get_columns("notes")}:
        op.drop_column("notes", "purged_at")
