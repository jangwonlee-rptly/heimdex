"""
SQLAlchemy Models for Heimdex Database Schema.

This module defines the SQLAlchemy ORM models that represent the database
schema for the Heimdex application. It includes models for jobs, job events,
and other core entities.

The `Base` class is the declarative base for all models, and the `metadata_obj`
is used to define a consistent naming convention for database constraints.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    TIMESTAMP,
    CheckConstraint,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    desc,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

metadata_obj = MetaData(
    naming_convention={
        "ix": "idx_%(table_name)s__%(column_0_label)s",
        "uq": "uq_%(table_name)s__%(column_0_name)s",
        "ck": "ck_%(table_name)s__%(constraint_name)s",
        "fk": "fk_%(table_name)s__%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)


class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy models in the application.

    This class provides a common base for all ORM models, and it is configured
    with a `MetaData` object that defines a consistent naming convention for
    database constraints. This helps to ensure that index, unique constraint,
    and foreign key names are generated in a predictable and standardized way.
    """

    metadata = metadata_obj


class JobStatus(str, Enum):
    """
    Enumeration of allowed job status values.

    This enum defines the possible states in the job lifecycle, ensuring that
    the `status` field in the `Job` model is always one of these well-defined
    values.

    Attributes:
        QUEUED (str): The initial state of a job when it is first created.
        RUNNING (str): The state of a job while it is being processed by a
            worker.
        SUCCEEDED (str): The terminal state of a job that has completed
            successfully.
        FAILED (str): The terminal state of a job that has failed and may be
            retried.
        CANCELED (str): The terminal state of a job that has been manually
            canceled.
        DEAD_LETTER (str): The terminal state of a job that has failed all of
            its retry attempts.
    """

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"
    DEAD_LETTER = "dead_letter"


class BackoffPolicy(str, Enum):
    """
    Enumeration of backoff policies for retry scheduling.

    This enum defines the strategies that can be used to schedule retries for
    failed jobs.

    Attributes:
        NONE (str): No backoff policy; the job will not be retried.
        FIXED (str): A fixed backoff policy, where the delay between retries
            is constant.
        EXPONENTIAL (str): An exponential backoff policy, where the delay
            between retries increases exponentially.
    """

    NONE = "none"
    FIXED = "fixed"
    EXPONENTIAL = "exp"


class Job(Base):
    """
    Represents the durable ledger for all asynchronous jobs.

    This SQLAlchemy model maps to the `job` table in the database. It stores
    the operational state of jobs and serves as the primary source of truth for
    job status queries. The model includes support for org-scoped multi-tenancy,
    idempotent job creation, and configurable retry logic.

    The job lifecycle follows a state machine:
    `queued` → `running` → (`succeeded` | `failed` | `canceled` | `dead_letter`)

    Attributes:
        id (uuid.UUID): The globally unique identifier for the job.
        org_id (uuid.UUID): The organization/tenant identifier for RLS.
        type (str): The job type discriminator (e.g., 'mock_process').
        status (JobStatus): The current state of the job.
        attempt (int): The retry attempt counter.
        max_attempts (int): The maximum number of retry attempts.
        backoff_policy (BackoffPolicy): The backoff policy for retries.
        priority (int): The job priority (higher is more urgent).
        idempotency_key (str | None): A client-provided key for deduplication.
        requested_by (str | None): The user or service that requested the job.
        created_at (datetime): The timestamp when the job was created.
        updated_at (datetime): The timestamp when the job was last modified.
        started_at (datetime | None): The timestamp when job execution started.
        finished_at (datetime | None): The timestamp when the job reached a
            terminal state.
        last_error_code (str | None): An error classification code.
        last_error_message (str | None): A human-readable error message.
        events (list[JobEvent]): A relationship to the job's events.
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
    status: Mapped[JobStatus] = mapped_column(
        SAEnum(
            JobStatus,
            name="job_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=JobStatus.QUEUED,
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
    max_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=5,
        server_default=text("5"),
        comment="Maximum retry attempts before dead-lettering",
    )
    backoff_policy: Mapped[BackoffPolicy] = mapped_column(
        SAEnum(
            BackoffPolicy,
            name="job_backoff_policy",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=BackoffPolicy.EXPONENTIAL,
        server_default=text("'exp'"),
        comment="Backoff policy for retry scheduling",
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
        String(64),
        nullable=True,
        comment="Error classification (e.g., 'TIMEOUT', 'VALIDATION_ERROR')",
    )
    last_error_message: Mapped[str | None] = mapped_column(
        String(2048),
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
            "idx_job__org_id_idempotency_key",
            "org_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        # Composite index for org-scoped chronological queries
        Index("idx_job__org_id_created_at_desc", "org_id", desc("created_at")),
        # Index for status monitoring
        Index("idx_job__status_created_at", "status", "created_at"),
        # Ensure finished_at is populated for terminal states only
        CheckConstraint(
            "((status IN ('succeeded', 'failed', 'canceled', 'dead_letter') "
            "AND finished_at IS NOT NULL) OR "
            "(status IN ('queued', 'running') AND finished_at IS NULL))",
            name="status_finished_at_consistency",
        ),
        {"comment": "Durable ledger for asynchronous jobs with retry and idempotency support"},
    )

    def __repr__(self) -> str:
        return f"<Job(id={self.id}, org_id={self.org_id}, type={self.type}, status={self.status})>"


class JobEvent(Base):
    """
    Represents an immutable audit log of all job state transitions.

    This SQLAlchemy model maps to the `job_event` table. It provides a
    complete timeline of a job's state changes, which is invaluable for
    debugging, compliance, and analytics. Events are designed to be
    append-only and should never be modified.

    Attributes:
        id (uuid.UUID): The unique identifier for the event.
        job_id (uuid.UUID): A foreign key to the parent job.
        ts (datetime): The timestamp of when the event occurred.
        prev_status (str | None): The status of the job before the
            transition. This is `None` for the initial event.
        next_status (str): The status of the job after the transition.
        detail_json (dict | None): A JSONB field for storing additional
            event metadata, such as stage, progress, or error details.
        job (Job): A relationship to the parent `Job` object.
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
        Index("idx_job_event__job_id_ts", "job_id", "ts"),
        # Index for chronological queries
        Index("idx_job_event__ts", "ts"),
        {
            "comment": "Immutable audit log of job state transitions",
        },
    )

    def __repr__(self) -> str:
        status_flow = f"{self.prev_status} -> {self.next_status}"
        return f"<JobEvent(id={self.id}, job_id={self.job_id}, status={status_flow})>"
