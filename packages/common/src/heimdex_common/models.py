"""SQLAlchemy models for Heimdex database schema."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


class Job(Base):
    """
    Durable ledger for all asynchronous jobs.

    This table stores the operational state of jobs and is the primary source of truth
    for job status queries. It supports org-scoped multi-tenancy, idempotent job creation,
    and retry logic.

    State machine: queued → running → (succeeded | failed | canceled | dead_letter)
    """

    __tablename__ = "job"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        comment="Globally unique job identifier",
    )

    # Tenant & type
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="Organization/tenant identifier for RLS",
    )
    type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Job type discriminator (e.g., 'mock_process', 'drive_ingest')",
    )

    # State & control
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="queued",
        server_default=text("'queued'"),
        comment="Current job state",
    )
    attempt: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="Retry attempt counter (0 = first attempt)",
    )
    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="Job priority (higher = more urgent, future use)",
    )

    # Idempotency & attribution
    idempotency_key: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Client-provided key for deduplication",
    )
    requested_by: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="User/service that requested the job",
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        comment="Job creation timestamp",
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        onupdate=datetime.utcnow,
        comment="Last modification timestamp",
    )
    started_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        comment="When job execution started",
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        comment="When job reached terminal state",
    )

    # Error tracking
    last_error_code: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Error classification (e.g., 'TIMEOUT', 'VALIDATION_ERROR')",
    )
    last_error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Human-readable error detail",
    )

    # Relationships
    events: Mapped[list[JobEvent]] = relationship(
        "JobEvent",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="JobEvent.ts.desc()",
    )

    # Table-level constraints and indexes
    __table_args__ = (
        # Idempotency constraint (org_id + idempotency_key unique when key is not null)
        # Using Index with unique=True for partial unique constraint support
        Index(
            "uq_job_org_idempotency",
            "org_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        # Status enum constraint
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'canceled', 'dead_letter')",
            name="ck_job_status",
        ),
        # Composite index for org-scoped queue queries (hot path)
        Index("idx_job_org_status", "org_id", "status", "created_at"),
        # Index for job type monitoring
        Index("idx_job_type_status", "type", "status"),
        {"comment": "Durable ledger for asynchronous jobs with retry and idempotency support"},
    )

    def __repr__(self) -> str:
        return f"<Job(id={self.id}, org_id={self.org_id}, type={self.type}, status={self.status})>"


class JobEvent(Base):
    """
    Immutable audit log of all job state transitions.

    This table provides a complete timeline of job state changes for debugging,
    compliance, and analytics. Events are append-only and never modified.
    """

    __tablename__ = "job_event"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        comment="Unique event identifier",
    )

    # Foreign key to job
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job.id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to parent job",
    )

    # Event data
    ts: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        comment="Event occurrence timestamp",
    )
    prev_status: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Status before transition (NULL for initial state)",
    )
    next_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Status after transition",
    )
    detail_json: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Additional event metadata (stage, progress, error details)",
    )

    # Relationships
    job: Mapped[Job] = relationship("Job", back_populates="events")

    # Table-level constraints and indexes
    __table_args__ = (
        # Index for job timeline queries (hot path)
        Index("idx_job_event_job_ts", "job_id", "ts"),
        # Index for chronological queries
        Index("idx_job_event_ts", "ts"),
        {
            "comment": "Immutable audit log of job state transitions",
        },
    )

    def __repr__(self) -> str:
        status_flow = f"{self.prev_status} -> {self.next_status}"
        return f"<JobEvent(id={self.id}, job_id={self.job_id}, status={status_flow})>"
