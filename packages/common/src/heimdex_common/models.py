"""
SQLAlchemy Models Defining the Heimdex Database Schema.

This module serves as the canonical, code-first definition of the Heimdex
database schema using the SQLAlchemy Object-Relational Mapper (ORM). By defining
the schema in Python, we gain type safety, maintainability, and a single source
of truth that is decoupled from any specific database vendor.

The models herein represent the core entities of the application, such as Jobs
and their associated Events. Each class maps to a database table, and its
attributes map to the columns of that table.

A key feature of this module is the consistent naming convention for database
constraints (indexes, keys, etc.), which is configured in the `metadata_obj`.
This ensures that the generated database schema is predictable and easy for
developers and DBAs to understand.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
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

# A custom MetaData instance with a standardized naming convention.
# This is a best practice that prevents auto-generated constraint names
# from being long and unpredictable (e.g., "uq_job_org_id_idempotency_key_1").
# Instead, they will follow a clear, consistent pattern.
metadata_obj = MetaData(
    naming_convention={
        "ix": "idx_%(table_name)s__%(column_0_label)s",  # Index
        "uq": "uq_%(table_name)s__%(column_0_name)s",  # Unique Constraint
        "ck": "ck_%(table_name)s__%(constraint_name)s",  # Check Constraint
        "fk": "fk_%(table_name)s__%(referred_table_name)s",  # Foreign Key
        "pk": "pk_%(table_name)s",  # Primary Key
    }
)


class Base(DeclarativeBase):
    """
    A common declarative base for all SQLAlchemy models in the application.

    Using a shared `Base` class allows for the centralized application of
    configurations, such as the `MetaData` object with its naming convention.
    All ORM models in the application should inherit from this class.
    """

    metadata = metadata_obj


class JobStatus(str, Enum):
    """
    A type-safe enumeration of the allowed states in a job's lifecycle.

    Using a Python `Enum` and linking it to a database ENUM type via `SAEnum`
    provides multiple benefits:
    1.  **Application-Level Safety**: Prevents bugs from typos in status strings.
    2.  **Database-Level Integrity**: The database itself will reject any attempt
        to set an invalid status.
    3.  **Self-Documentation**: The code clearly defines all possible states.

    The lifecycle transitions are typically:
    `QUEUED` -> `RUNNING` -> (`SUCCEEDED` | `FAILED` -> `QUEUED` (retry)) -> `DEAD_LETTER`
    """

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"
    DEAD_LETTER = "dead_letter"


class BackoffPolicy(str, Enum):
    """
    Enumeration of retry scheduling strategies for failed jobs.
    """

    NONE = "none"  # The job will not be retried.
    FIXED = "fixed"  # The delay between retries is constant.
    EXPONENTIAL = "exp"  # The delay increases exponentially with each retry.


class Job(Base):
    """
    Represents the durable state and control record for an asynchronous job.

    This model is the central ledger for all background processing tasks. It is
    designed for high-concurrency environments and includes features critical for
    a robust job queueing system, such as multi-tenancy, idempotency, and
    configurable retry logic. It is the source of truth for a job's status.

    Attributes:
        id: The primary key, a globally unique identifier for the job.
        org_id: The tenant identifier, crucial for data isolation and RLS.
        type: A string discriminator for routing the job to the correct handler.
        status: The current state in the job lifecycle (`JobStatus`).
        attempt: The current retry count (0 for the first attempt).
        max_attempts: The number of retries before moving the job to dead-letter.
        backoff_policy: The strategy for calculating retry delays.
        idempotency_key: A client-provided key to prevent duplicate job creation.
        created_at: The timestamp of job creation.
        updated_at: The timestamp of the last modification to the job record.
        events: A one-to-many relationship to the job's historical events.
    """

    __tablename__ = "job"

    # Core Identifiers
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(100), nullable=False)

    # State Machine and Retry Control
    status: Mapped[JobStatus] = mapped_column(
        SAEnum(JobStatus, name="job_status", values_callable=lambda e: [i.value for i in e]),
        nullable=False,
        default=JobStatus.QUEUED,
        server_default=text("'queued'"),
    )
    attempt: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=5, server_default=text("5")
    )
    backoff_policy: Mapped[BackoffPolicy] = mapped_column(
        SAEnum(
            BackoffPolicy, name="job_backoff_policy", values_callable=lambda e: [i.value for i in e]
        ),
        nullable=False,
        default=BackoffPolicy.EXPONENTIAL,
        server_default=text("'exp'"),
    )
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    # Idempotency and Attribution
    idempotency_key: Mapped[str | None] = mapped_column(String(255))
    job_key: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True
    )  # Server-side deterministic idempotency key (SHA256 hash)
    requested_by: Mapped[str | None] = mapped_column(String(255))

    # Timestamps for Auditing and Analytics
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        onupdate=datetime.utcnow,
    )
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    # Error Tracking
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    last_error_message: Mapped[str | None] = mapped_column(String(2048))

    # Relationships
    events: Mapped[list[JobEvent]] = relationship(
        "JobEvent",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="JobEvent.ts.desc()",
    )

    __table_args__ = (
        # Partial unique index for idempotency. This is a key optimization. It
        # enforces that for a given organization, the idempotency_key must be
        # unique, but only when it's not NULL. This allows clients to retry
        # job creation safely without creating duplicate jobs.
        Index(
            "idx_job__org_id_idempotency_key",
            "org_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        # A composite index to optimize the most common query pattern: fetching
        # the most recent jobs for a specific organization.
        Index("idx_job__org_id_created_at_desc", "org_id", desc("created_at")),
        # An index to efficiently query for jobs in a particular state, which is
        # essential for workers picking up new jobs or for monitoring failures.
        Index("idx_job__status_created_at", "status", "created_at"),
        # A database-level check constraint to enforce application logic. This
        # ensures data integrity by requiring `finished_at` to be set if and
        # only if the job is in a terminal state.
        CheckConstraint(
            "((status IN ('succeeded', 'failed', 'canceled', 'dead_letter')) "
            "AND finished_at IS NOT NULL) OR "
            "((status IN ('queued', 'running')) AND finished_at IS NULL)",
            name="status_finished_at_consistency",
        ),
        {"comment": "Durable ledger for asynchronous jobs with retry and idempotency support"},
    )

    def __repr__(self) -> str:
        return f"<Job(id={self.id}, org_id={self.org_id}, type={self.type}, status={self.status})>"


class JobEvent(Base):
    """
    Represents an immutable, append-only audit log of a job's lifecycle.

    This model provides a complete, chronological history of every state
    transition and significant event that occurs during a job's execution. It is
    invaluable for debugging, auditing, and observability, as it allows developers
    to reconstruct the exact sequence of events for any given job.

    Attributes:
        id: The primary key for the event.
        job_id: A foreign key linking this event to its parent `Job`.
        ts: The precise timestamp when the event occurred.
        prev_status: The state of the job before this event.
        next_status: The state of the job after this event.
        detail_json: A flexible JSONB field for storing rich, structured context.
        job: The back-referencing relationship to the parent `Job`.
    """

    __tablename__ = "job_event"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    # The `ondelete="CASCADE"` ensures that if a Job is deleted, all of its
    # associated events are automatically deleted by the database, preventing
    # orphaned records.
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job.id", ondelete="CASCADE"), nullable=False
    )
    ts: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )
    prev_status: Mapped[str | None] = mapped_column(String(50))
    next_status: Mapped[str] = mapped_column(String(50), nullable=False)
    # JSONB is used here because it's a binary, indexed format in PostgreSQL,
    # making it more efficient for storage and querying than plain JSON or text.
    detail_json: Mapped[dict | None] = mapped_column(JSONB)

    job: Mapped[Job] = relationship("Job", back_populates="events")

    __table_args__ = (
        # A composite index to optimize for the most common query: fetching all
        # events for a specific job, ordered by time.
        Index("idx_job_event__job_id_ts", "job_id", "ts"),
        # A general-purpose index on the timestamp for chronological queries
        # across all jobs, which can be useful for system-wide monitoring.
        Index("idx_job_event__ts", "ts"),
        {"comment": "Immutable audit log of job state transitions"},
    )

    def __repr__(self) -> str:
        status_flow = f"{self.prev_status} -> {self.next_status}"
        return f"<JobEvent(id={self.id}, job_id={self.job_id}, status='{status_flow}')>"


class Outbox(Base):
    """
    Transactional Outbox for Reliable Message Publishing.

    This model implements the transactional outbox pattern, ensuring exactly-once
    message delivery semantics between the database and the message broker. By
    writing both the job record and the outbox message within the same database
    transaction, we eliminate the split-brain problem where a job exists in the
    database but was never published to the queue, or vice versa.

    The outbox dispatcher service reads unsent messages from this table and
    publishes them to Dramatiq, marking them as sent only after successful
    broker acknowledgment.

    Attributes:
        id: The primary key, auto-incrementing BIGSERIAL for performance.
        job_id: Foreign key to the job this message is for.
        task_name: The name of the Dramatiq actor to invoke (e.g., "process_mock").
        payload: JSONB containing the message arguments and metadata.
        sent_at: Timestamp of successful publish; NULL indicates pending.
        fail_count: Number of failed publish attempts for retry logic.
        last_error: The most recent error message from a failed publish attempt.
        created_at: Timestamp of outbox record creation.
    """

    __tablename__ = "outbox"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_name: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    fail_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    last_error: Mapped[str | None] = mapped_column(String(2048))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        # Critical index for the outbox dispatcher to efficiently find unsent messages.
        # Uses a partial index (WHERE sent_at IS NULL) to keep the index small and fast.
        Index("idx_outbox_unsent", "created_at", postgresql_where=text("sent_at IS NULL")),
        # Index on job_id for finding all outbox records related to a specific job.
        {"comment": "Transactional outbox for exactly-once message delivery"},
    )

    def __repr__(self) -> str:
        status = "sent" if self.sent_at else "pending"
        return (
            f"<Outbox(id={self.id}, job_id={self.job_id}, "
            f"task={self.task_name}, status={status})>"
        )
