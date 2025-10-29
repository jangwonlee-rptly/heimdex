"""
Repository for Job and JobEvent Data Access.

This module provides the `JobRepository` class, which encapsulates the data
access logic for the `Job` and `JobEvent` models. It provides a clean and
consistent interface for creating, retrieving, and updating job-related
data in the database.
"""

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
    Manages database operations for the `Job` and `JobEvent` models.

    This repository provides a clean abstraction over the SQLAlchemy models,
    ensuring that all data access follows consistent patterns and that
    business logic related to data manipulation is centralized.

    Attributes:
        session (Session): The SQLAlchemy session for database operations.
    """

    def __init__(self, session: Session):
        """
        Initializes the repository with a SQLAlchemy session.

        Args:
            session (Session): An active SQLAlchemy session to be used for
                database operations.
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
        Creates a new job in the 'queued' state.

        This method creates a new `Job` instance and its initial `JobEvent`.

        Args:
            org_id (uuid.UUID): The organization/tenant identifier.
            job_type (str): The job type discriminator (e.g.,
                'mock_process').
            idempotency_key (str | None): An optional client-provided key for
                deduplication.
            requested_by (str | None): An optional user or service attribution.
            priority (int): The job priority (higher is more urgent).

        Returns:
            Job: The newly created `Job` instance.

        Raises:
            sqlalchemy.exc.IntegrityError: If the `idempotency_key` already
                exists for the given `org_id`.
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
        Retrieves a job by its unique identifier.

        Args:
            job_id (uuid.UUID): The UUID of the job to retrieve.

        Returns:
            Job | None: The `Job` instance if found, otherwise `None`.
        """
        stmt = select(Job).where(Job.id == job_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def get_job_with_events(self, job_id: uuid.UUID) -> Job | None:
        """
        Retrieves a job with all of its events eagerly loaded.

        Args:
            job_id (uuid.UUID): The UUID of the job to retrieve.

        Returns:
            Job | None: The `Job` instance with its `events` relationship
                populated, or `None` if the job is not found.
        """
        stmt = select(Job).options(selectinload(Job.events)).where(Job.id == job_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def get_latest_job_event(self, job_id: uuid.UUID) -> JobEvent | None:
        """
        Gets the most recent event for a given job.

        Args:
            job_id (uuid.UUID): The UUID of the job.

        Returns:
            JobEvent | None: The latest `JobEvent` instance, or `None` if the
                job has no events.
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
        Updates a job's status and related fields.

        This method handles both the update of the `Job` record and the
        logging of a corresponding `JobEvent` in a single operation to
        maintain data consistency.

        Args:
            job_id (uuid.UUID): The UUID of the job to update.
            status (str | None): The new status value.
            last_error_code (str | None): An error classification code.
            last_error_message (str | None): A human-readable error message.
            started_at (datetime | None): The timestamp of when job execution
                started.
            finished_at (datetime | None): The timestamp of when the job
                reached a terminal state.
            log_event (bool): Whether to log a `JobEvent`. Defaults to `True`.
            event_detail (dict[str, Any] | None): Additional event metadata.

        Raises:
            ValueError: If the job with the specified `job_id` is not found.
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
        Updates a job with stage and progress information.

        This method is a convenience wrapper around `update_job_status` that
        provides backward compatibility with older schemas by storing stage,
        progress, and result in the `JobEvent` log.

        Args:
            job_id (uuid.UUID): The UUID of the job to update.
            status (str | None): The new status value.
            stage (str | None): The current processing stage.
            progress (int | None): The progress percentage (0-100).
            result (dict[str, Any] | None): The job's result data.
            error (str | None): An error message.

        Raises:
            ValueError: If the job with the specified `job_id` is not found.
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
        Creates an immutable audit log entry for a job state transition.

        Args:
            job_id (uuid.UUID): The UUID of the parent job.
            prev_status (str | None): The status before the transition.
            next_status (str): The status after the transition.
            detail_json (dict[str, Any] | None): Additional event metadata.

        Returns:
            JobEvent: The created `JobEvent` instance.
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
        Retrieves queued jobs, ordered by priority and creation time.

        Args:
            org_id (uuid.UUID): The organization identifier.
            limit (int): The maximum number of jobs to return.
            job_type (str | None): An optional filter by job type.

        Returns:
            Sequence[Job]: A list of `Job` instances in the queued state.
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
        Retrieves jobs for an organization, filtered by status.

        Args:
            org_id (uuid.UUID): The organization identifier.
            status (str): The status to filter by.
            limit (int): The maximum number of jobs to return.

        Returns:
            Sequence[Job]: A list of `Job` instances with the specified
                status.
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
        Gets job count statistics by status for an organization.

        Args:
            org_id (uuid.UUID): The organization identifier.

        Returns:
            dict[str, int]: A dictionary mapping status values to job counts.
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
        Increments the retry attempt counter for a job.

        Args:
            job_id (uuid.UUID): The UUID of the job.

        Raises:
            ValueError: If the job with the specified `job_id` is not found.
        """
        job = self.get_job_by_id(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        job.attempt += 1
        job.updated_at = datetime.now(UTC)
        self.session.flush()
