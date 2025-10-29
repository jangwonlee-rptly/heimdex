"""Repository for Job and JobEvent data access."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from ..models import Job, JobEvent, JobStatus


class JobRepository:
    """
    Repository for managing Job and JobEvent database operations.

    This repository provides a clean abstraction over SQLAlchemy models,
    ensuring consistent data access patterns and business logic enforcement.
    """

    def __init__(self, session: Session):
        """
        Initialize the repository with a SQLAlchemy session.

        Args:
            session: Active SQLAlchemy session for database operations
        """
        self.session = session

    def create_job(
        self,
        org_id: uuid.UUID,
        job_type: str,
        idempotency_key: str | None = None,
        requested_by: str | None = None,
        priority: int = 0,
    ) -> Job:
        """
        Create a new job in queued state.

        Args:
            org_id: Organization/tenant identifier
            job_type: Job type discriminator (e.g., 'mock_process', 'drive_ingest')
            idempotency_key: Optional client-provided deduplication key
            requested_by: Optional user/service attribution
            priority: Job priority (higher = more urgent, default: 0)

        Returns:
            The newly created Job instance

        Raises:
            sqlalchemy.exc.IntegrityError: If idempotency_key already exists for org_id
        """
        job = Job(
            id=uuid.uuid4(),
            org_id=org_id,
            type=job_type,
            status=JobStatus.QUEUED,
            attempt=0,
            priority=priority,
            idempotency_key=idempotency_key,
            requested_by=requested_by,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self.session.add(job)
        self.session.flush()  # Get ID without committing transaction

        # Log initial job event
        self.log_job_event(
            job_id=job.id,
            prev_status=None,
            next_status=JobStatus.QUEUED.value,
            detail_json=None,
        )

        return job

    def get_job_by_id(self, job_id: uuid.UUID) -> Job | None:
        """
        Retrieve a job by its ID.

        Args:
            job_id: The UUID of the job to retrieve

        Returns:
            The Job instance if found, None otherwise
        """
        stmt = select(Job).where(Job.id == job_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def get_job_with_events(self, job_id: uuid.UUID) -> Job | None:
        """
        Retrieve a job with all its events eagerly loaded.

        Args:
            job_id: The UUID of the job to retrieve

        Returns:
            The Job instance with events loaded, None if not found
        """
        stmt = select(Job).options(selectinload(Job.events)).where(Job.id == job_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def get_latest_job_event(self, job_id: uuid.UUID) -> JobEvent | None:
        """
        Get the most recent event for a job.

        Args:
            job_id: The UUID of the job

        Returns:
            The latest JobEvent instance, None if no events exist
        """
        stmt = (
            select(JobEvent).where(JobEvent.job_id == job_id).order_by(desc(JobEvent.ts)).limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def update_job_status(
        self,
        job_id: uuid.UUID,
        status: str | None = None,
        last_error_code: str | None = None,
        last_error_message: str | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        log_event: bool = True,
        event_detail: dict[str, Any] | None = None,
    ) -> None:
        """
        Update a job's status and related fields.

        This method handles both the job update and optional event logging
        in a single operation to maintain consistency.

        Args:
            job_id: The UUID of the job to update
            status: New status value (if provided)
            last_error_code: Error classification code (if error occurred)
            last_error_message: Human-readable error message (if error occurred)
            started_at: Timestamp when job execution started
            finished_at: Timestamp when job reached terminal state
            log_event: Whether to log a job event (default: True)
            event_detail: Additional event metadata (stage, progress, etc.)

        Raises:
            ValueError: If job not found
        """
        job = self.get_job_by_id(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        prev_status = job.status
        status_enum: JobStatus | None = None

        # Update job fields
        if status is not None:
            status_enum = status if isinstance(status, JobStatus) else JobStatus(status)
            job.status = status_enum
        if last_error_code is not None:
            job.last_error_code = last_error_code
        if last_error_message is not None:
            job.last_error_message = last_error_message[:2048]
        if started_at is not None:
            job.started_at = started_at
        if finished_at is not None:
            job.finished_at = finished_at

        # Always update updated_at
        job.updated_at = datetime.now(UTC)

        self.session.flush()

        # Log event if status changed and logging enabled
        if log_event and status_enum is not None and prev_status != status_enum:
            self.log_job_event(
                job_id=job_id,
                prev_status=(
                    prev_status.value if isinstance(prev_status, JobStatus) else prev_status
                ),
                next_status=status_enum.value,
                detail_json=event_detail,
            )

    def update_job_with_stage_progress(
        self,
        job_id: uuid.UUID,
        status: str | None = None,
        stage: str | None = None,
        progress: int | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        """
        Update job with stage/progress information (legacy compatibility).

        This method provides backward compatibility with the old schema by
        storing stage, progress, and result in the event log rather than
        the job table.

        Args:
            job_id: The UUID of the job to update
            status: New status value
            stage: Current processing stage (stored in event detail)
            progress: Progress percentage 0-100 (stored in event detail)
            result: Job result data (stored in event detail)
            error: Error message (stored as last_error_message)

        Raises:
            ValueError: If job not found
        """
        job = self.get_job_by_id(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        # Build event detail from stage/progress/result
        event_detail: dict[str, Any] = {}
        if stage is not None:
            event_detail["stage"] = stage
        if progress is not None:
            event_detail["progress"] = progress
        if result is not None:
            event_detail["result"] = result

        status_enum = None
        if status is not None:
            status_enum = status if isinstance(status, JobStatus) else JobStatus(status)

        # Set timestamps based on status transitions
        started_at = None
        finished_at = None
        if status_enum == JobStatus.RUNNING and job.status != JobStatus.RUNNING:
            started_at = datetime.now(UTC)
        if status_enum in {
            JobStatus.SUCCEEDED,
            JobStatus.FAILED,
            JobStatus.CANCELED,
            JobStatus.DEAD_LETTER,
        }:
            finished_at = datetime.now(UTC)

        # Update job
        self.update_job_status(
            job_id=job_id,
            status=status_enum.value if status_enum is not None else None,
            last_error_message=error,
            started_at=started_at,
            finished_at=finished_at,
            log_event=True,
            event_detail=event_detail if event_detail else None,
        )

    def log_job_event(
        self,
        job_id: uuid.UUID,
        prev_status: str | None,
        next_status: str,
        detail_json: dict[str, Any] | None = None,
    ) -> JobEvent:
        """
        Create an immutable audit log entry for a job state transition.

        Args:
            job_id: The UUID of the job
            prev_status: Status before transition (None for initial state)
            next_status: Status after transition
            detail_json: Additional event metadata (stage, progress, error details)

        Returns:
            The created JobEvent instance
        """
        event = JobEvent(
            id=uuid.uuid4(),
            job_id=job_id,
            ts=datetime.now(UTC),
            prev_status=prev_status,
            next_status=next_status,
            detail_json=detail_json,
        )
        self.session.add(event)
        self.session.flush()
        return event

    def get_queued_jobs(
        self,
        org_id: uuid.UUID,
        limit: int = 10,
        job_type: str | None = None,
    ) -> Sequence[Job]:
        """
        Retrieve queued jobs for an organization, ordered by priority and creation time.

        Args:
            org_id: Organization identifier
            limit: Maximum number of jobs to return (default: 10)
            job_type: Optional filter by job type

        Returns:
            List of Job instances in queued state
        """
        stmt = (
            select(Job)
            .where(Job.org_id == org_id, Job.status == JobStatus.QUEUED)
            .order_by(desc(Job.priority), Job.created_at)
            .limit(limit)
        )

        if job_type is not None:
            stmt = stmt.where(Job.type == job_type)

        return self.session.execute(stmt).scalars().all()

    def get_jobs_by_status(
        self,
        org_id: uuid.UUID,
        status: str,
        limit: int = 100,
    ) -> Sequence[Job]:
        """
        Retrieve jobs by status for an organization.

        Args:
            org_id: Organization identifier
            status: Status to filter by
            limit: Maximum number of jobs to return (default: 100)

        Returns:
            List of Job instances with the specified status
        """
        status_enum = status if isinstance(status, JobStatus) else JobStatus(status)
        stmt = (
            select(Job)
            .where(Job.org_id == org_id, Job.status == status_enum)
            .order_by(desc(Job.created_at))
            .limit(limit)
        )
        return self.session.execute(stmt).scalars().all()

    def get_job_statistics(self, org_id: uuid.UUID) -> dict[str, int]:
        """
        Get job count statistics by status for an organization.

        Args:
            org_id: Organization identifier

        Returns:
            Dictionary mapping status values to job counts
        """
        stmt = (
            select(Job.status, func.count(Job.id)).where(Job.org_id == org_id).group_by(Job.status)
        )
        results = self.session.execute(stmt).all()

        return {
            (status.value if isinstance(status, JobStatus) else status): count
            for status, count in results
        }

    def increment_attempt(self, job_id: uuid.UUID) -> None:
        """
        Increment the retry attempt counter for a job.

        Args:
            job_id: The UUID of the job

        Raises:
            ValueError: If job not found
        """
        job = self.get_job_by_id(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        job.attempt += 1
        job.updated_at = datetime.now(UTC)
        self.session.flush()
