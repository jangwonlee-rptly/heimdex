"""add_outbox_table_for_transactional_publish

Creates the outbox table to implement the transactional outbox pattern for
exactly-once message delivery. This eliminates split-brain between database
commits and broker enqueues by writing both the job record and the outbox
message in a single atomic transaction.

The outbox dispatcher service reads unsent messages (sent_at IS NULL) and
publishes them to the message broker, marking them as sent only after
successful broker acknowledgment.

Revision ID: 4565a99c19e4
Revises: 3c5dd155fcde
Create Date: 2025-10-30 16:06:51.173064

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "4565a99c19e4"
down_revision = "3c5dd155fcde"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create outbox table for transactional message publishing."""
    op.create_table(
        "outbox",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_name", sa.String(length=100), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sent_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("fail_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_error", sa.String(length=2048), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["job_id"], ["job.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        comment="Transactional outbox for exactly-once message delivery",
    )

    # Index for efficient lookups of a job's outbox messages
    op.create_index("idx_outbox__job_id", "outbox", ["job_id"], unique=False)

    # Critical partial index for the outbox dispatcher to find unsent messages quickly
    op.create_index(
        "idx_outbox_unsent",
        "outbox",
        ["created_at"],
        unique=False,
        postgresql_where=sa.text("sent_at IS NULL"),
    )


def downgrade() -> None:
    """Drop outbox table and its indexes."""
    op.drop_index("idx_outbox_unsent", table_name="outbox")
    op.drop_index("idx_outbox__job_id", table_name="outbox")
    op.drop_table("outbox")
