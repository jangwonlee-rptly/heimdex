"""hardening: job ledger enums/indexes/idempotency

Revision ID: 3af4686817cc
Revises: 001_job_ledger_init
Create Date: 2025-10-29 06:05:04.494436

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "3af4686817cc"
down_revision = "001_job_ledger_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    job_status_values = (
        "queued",
        "running",
        "succeeded",
        "failed",
        "canceled",
        "dead_letter",
    )
    job_backoff_values = ("none", "fixed", "exp")

    job_status_enum = sa.Enum(*job_status_values, name="job_status")
    backoff_policy_enum = sa.Enum(*job_backoff_values, name="job_backoff_policy")

    bind = op.get_bind()

    job_status_enum.create(bind, checkfirst=True)
    backoff_policy_enum.create(bind, checkfirst=True)

    # Normalize legacy statuses to the new canonical values prior to enum conversion
    op.execute(sa.text("UPDATE job SET status = 'queued' WHERE status IN ('pending', 'queued')"))
    op.execute(
        sa.text("UPDATE job SET status = 'running' WHERE status IN ('processing', 'running')")
    )
    op.execute(
        sa.text("UPDATE job SET status = 'succeeded' WHERE status IN ('completed', 'succeeded')")
    )

    op.add_column(
        "job",
        sa.Column(
            "max_attempts",
            sa.Integer(),
            server_default=sa.text("5"),
            nullable=False,
            comment="Maximum retry attempts before dead-lettering",
        ),
    )
    op.add_column(
        "job",
        sa.Column(
            "backoff_policy",
            backoff_policy_enum,
            server_default=sa.text("'exp'::job_backoff_policy"),
            nullable=False,
            comment="Backoff policy for retry scheduling",
        ),
    )

    op.execute(sa.text("ALTER TABLE job ALTER COLUMN status DROP DEFAULT"))
    op.alter_column(
        "job",
        "status",
        existing_type=sa.VARCHAR(length=50),
        type_=job_status_enum,
        existing_comment="Current job state",
        existing_nullable=False,
        postgresql_using="status::job_status",
    )
    op.execute(sa.text("ALTER TABLE job ALTER COLUMN status SET DEFAULT 'queued'::job_status"))

    op.alter_column(
        "job",
        "last_error_code",
        existing_type=sa.VARCHAR(length=100),
        type_=sa.String(length=64),
        existing_comment="Error classification (e.g., 'TIMEOUT', 'VALIDATION_ERROR')",
        existing_nullable=True,
    )
    op.alter_column(
        "job",
        "last_error_message",
        existing_type=sa.TEXT(),
        type_=sa.String(length=2048),
        existing_comment="Human-readable error detail",
        existing_nullable=True,
    )

    op.drop_index(op.f("idx_job_org_status"), table_name="job")
    op.drop_index(op.f("idx_job_type_status"), table_name="job")
    op.drop_index(
        op.f("uq_job_org_idempotency"),
        table_name="job",
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.create_index(op.f("idx_job__job_org_id"), "job", ["org_id"], unique=False)
    op.create_index(
        "idx_job__org_id_created_at_desc",
        "job",
        ["org_id", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "idx_job__org_id_idempotency_key",
        "job",
        ["org_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.create_index(
        "idx_job__status_created_at",
        "job",
        ["status", "created_at"],
        unique=False,
    )

    op.create_check_constraint(
        "status_finished_at_consistency",
        "job",
        sa.text(
            "("
            "status IN ('succeeded', 'failed', 'canceled', 'dead_letter') "
            "AND finished_at IS NOT NULL"
            ") OR ("
            "status IN ('queued', 'running') AND finished_at IS NULL"
            ")"
        ),
    )

    op.drop_index(op.f("idx_job_event_job_ts"), table_name="job_event")
    op.drop_index(op.f("idx_job_event_ts"), table_name="job_event")
    op.create_index("idx_job_event__job_id_ts", "job_event", ["job_id", "ts"], unique=False)
    op.create_index("idx_job_event__ts", "job_event", ["ts"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_job_event__ts", table_name="job_event")
    op.drop_index("idx_job_event__job_id_ts", table_name="job_event")
    op.create_index(op.f("idx_job_event_ts"), "job_event", ["ts"], unique=False)
    op.create_index(op.f("idx_job_event_job_ts"), "job_event", ["job_id", "ts"], unique=False)

    op.drop_constraint(
        op.f("ck_job__status_finished_at_consistency"),
        "job",
        type_="check",
    )

    op.drop_index("idx_job__status_created_at", table_name="job")
    op.drop_index(
        "idx_job__org_id_idempotency_key",
        table_name="job",
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.drop_index("idx_job__org_id_created_at_desc", table_name="job")
    op.drop_index(op.f("idx_job__job_org_id"), table_name="job")

    op.create_index(
        op.f("uq_job_org_idempotency"),
        "job",
        ["org_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.create_index(op.f("idx_job_type_status"), "job", ["type", "status"], unique=False)
    op.create_index(
        op.f("idx_job_org_status"), "job", ["org_id", "status", "created_at"], unique=False
    )

    op.alter_column(
        "job",
        "last_error_message",
        existing_type=sa.String(length=2048),
        type_=sa.TEXT(),
        existing_comment="Human-readable error detail",
        existing_nullable=True,
    )
    op.alter_column(
        "job",
        "last_error_code",
        existing_type=sa.String(length=64),
        type_=sa.VARCHAR(length=100),
        existing_comment="Error classification (e.g., 'TIMEOUT', 'VALIDATION_ERROR')",
        existing_nullable=True,
    )
    op.execute(sa.text("ALTER TABLE job ALTER COLUMN status DROP DEFAULT"))
    op.alter_column(
        "job",
        "status",
        existing_type=sa.Enum(
            "queued",
            "running",
            "succeeded",
            "failed",
            "canceled",
            "dead_letter",
            name="job_status",
        ),
        type_=sa.VARCHAR(length=50),
        existing_comment="Current job state",
        existing_nullable=False,
        postgresql_using="status::text",
    )
    op.execute(
        sa.text("ALTER TABLE job ALTER COLUMN status SET DEFAULT 'queued'::character varying")
    )

    op.drop_column("job", "backoff_policy")
    op.drop_column("job", "max_attempts")

    bind = op.get_bind()
    sa.Enum(name="job_backoff_policy").drop(bind, checkfirst=True)
    sa.Enum(name="job_status").drop(bind, checkfirst=True)
