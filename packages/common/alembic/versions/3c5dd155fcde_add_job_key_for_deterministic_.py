"""add_job_key_for_deterministic_idempotency

Adds a server-side deterministic job_key column to the job table for robust
idempotency. The job_key is computed as SHA256(org_id:op_type:payload) and
enforces uniqueness at the database level, preventing duplicate job creation.

This migration:
1. Adds job_key column as nullable
2. Backfills existing rows with a hash based on job ID (for legacy compatibility)
3. Creates a unique index on job_key
4. Alters the column to NOT NULL

Revision ID: 3c5dd155fcde
Revises: 3af4686817cc
Create Date: 2025-10-30 16:06:06.946911

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "3c5dd155fcde"
down_revision = "3af4686817cc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add job_key column for deterministic server-side idempotency."""
    # Step 1: Add job_key column as nullable TEXT
    op.add_column(
        "job",
        sa.Column("job_key", sa.String(length=64), nullable=True),
    )

    # Step 2: Backfill existing rows with a deterministic hash based on their ID
    # This ensures existing jobs have a job_key (for legacy compatibility)
    # Future jobs will have job_key computed from org_id:type:payload
    op.execute(
        sa.text(
            """
            UPDATE job
            SET job_key = encode(sha256(CAST(id AS TEXT)::bytea), 'hex')
            WHERE job_key IS NULL
            """
        )
    )

    # Step 3: Create unique index on job_key
    op.create_index(
        "idx_job__job_key",
        "job",
        ["job_key"],
        unique=True,
    )

    # Step 4: Alter column to NOT NULL now that all rows have values
    op.alter_column("job", "job_key", nullable=False)


def downgrade() -> None:
    """Remove job_key column and its index."""
    # Drop the unique index first
    op.drop_index("idx_job__job_key", table_name="job")

    # Drop the column
    op.drop_column("job", "job_key")
