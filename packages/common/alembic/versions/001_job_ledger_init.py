"""Initial job ledger schema with job and job_event tables

Revision ID: 001_job_ledger_init
Revises:
Create Date: 2025-10-28

This migration establishes the canonical durable job ledger with:
- job table: operational state for async jobs (replaces old jobs table)
- job_event table: immutable audit log for state transitions

The schema supports:
- Multi-tenancy via org_id (for future RLS in Supabase)
- Idempotent job creation via idempotency_key
- Retry logic with attempt counter
- State machine: queued → running → (succeeded|failed|canceled|dead_letter)
- Full audit trail of all state transitions
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "001_job_ledger_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop old jobs table if it exists (superseded by new schema)
    op.execute("DROP TABLE IF EXISTS jobs CASCADE")

    # Create job table
    op.create_table(
        "job",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
            comment="Globally unique job identifier",
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Organization/tenant identifier for RLS",
        ),
        sa.Column(
            "type",
            sa.String(length=100),
            nullable=False,
            comment="Job type discriminator (e.g., 'mock_process', 'drive_ingest')",
        ),
        sa.Column(
            "status",
            sa.String(length=50),
            server_default=sa.text("'queued'"),
            nullable=False,
            comment="Current job state",
        ),
        sa.Column(
            "attempt",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Retry attempt counter (0 = first attempt)",
        ),
        sa.Column(
            "priority",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Job priority (higher = more urgent, future use)",
        ),
        sa.Column(
            "idempotency_key",
            sa.String(length=255),
            nullable=True,
            comment="Client-provided key for deduplication",
        ),
        sa.Column(
            "requested_by",
            sa.String(length=255),
            nullable=True,
            comment="User/service that requested the job",
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
            comment="Job creation timestamp",
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
            comment="Last modification timestamp",
        ),
        sa.Column(
            "started_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
            comment="When job execution started",
        ),
        sa.Column(
            "finished_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
            comment="When job reached terminal state",
        ),
        sa.Column(
            "last_error_code",
            sa.String(length=100),
            nullable=True,
            comment="Error classification (e.g., 'TIMEOUT', 'VALIDATION_ERROR')",
        ),
        sa.Column(
            "last_error_message",
            sa.Text(),
            nullable=True,
            comment="Human-readable error detail",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_job"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'canceled', 'dead_letter')",
            name="ck_job_status",
        ),
        comment="Durable ledger for asynchronous jobs with retry and idempotency support",
    )

    # Unique constraint for idempotency key within org_id
    # this fixes the postgresql_where issue
    op.create_index(
        "uq_job_org_idempotency",
        "job",
        ["org_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    # Create indexes for job table
    op.create_index(
        "idx_job_org_status",
        "job",
        ["org_id", "status", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_job_type_status",
        "job",
        ["type", "status"],
        unique=False,
    )

    # Create job_event table
    op.create_table(
        "job_event",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
            comment="Unique event identifier",
        ),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Reference to parent job",
        ),
        sa.Column(
            "ts",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
            comment="Event occurrence timestamp",
        ),
        sa.Column(
            "prev_status",
            sa.String(length=50),
            nullable=True,
            comment="Status before transition (NULL for initial state)",
        ),
        sa.Column(
            "next_status",
            sa.String(length=50),
            nullable=False,
            comment="Status after transition",
        ),
        sa.Column(
            "detail_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Additional event metadata (stage, progress, error details)",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_job_event"),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["job.id"],
            name="fk_job_event_job_id",
            ondelete="CASCADE",
        ),
        comment="Immutable audit log of job state transitions",
    )

    # Create indexes for job_event table
    op.create_index(
        "idx_job_event_job_ts",
        "job_event",
        ["job_id", "ts"],
        unique=False,
    )
    op.create_index(
        "idx_job_event_ts",
        "job_event",
        ["ts"],
        unique=False,
    )


def downgrade() -> None:
    # Drop job_event table (cascade will handle FK constraints)
    op.drop_table("job_event")

    # Drop job table
    op.drop_table("job")

    # Note: We do NOT recreate the old jobs table in downgrade
    # This is a forward-only migration in practice
