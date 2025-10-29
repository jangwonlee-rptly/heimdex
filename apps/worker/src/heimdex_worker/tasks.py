"""
Dramatiq Tasks for Background Job Processing.

This module defines the Dramatiq actors that perform the actual work of
processing asynchronous jobs. Actors are functions decorated with `@dramatiq.actor`
which are discovered and run by the Dramatiq worker process.

These tasks are responsible for:
-   Receiving job information from the message queue.
-   Executing the job's business logic (e.g., video processing, analysis).
-   Updating the job's status in the database via the `JobRepository`.
"""

from __future__ import annotations

import os
import time
import uuid
from datetime import UTC, datetime

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from heimdex_common.db import get_db
from heimdex_common.repositories import JobRepository

from .logger import log_event

# Configure Dramatiq broker
redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
broker = RedisBroker(url=redis_url)
dramatiq.set_broker(broker)

# Stage durations (seconds)
STAGE_DURATIONS = {
    "extracting": 2,
    "analyzing": 3,
    "indexing": 1,
}


def _update_job_status(
    job_id: str,
    status: str | None = None,
    stage: str | None = None,
    progress: int | None = None,
    result: dict | None = None,
    error: str | None = None,
) -> None:
    """
    Updates a job's status and logs a corresponding event.

    This helper function provides a consistent way for worker tasks to update
    the status of a job in the database. It uses the `JobRepository` to
    abstract the underlying database operations.

    The function also handles the mapping of legacy status values to the new
    `JobStatus` enum to maintain backward compatibility.

    Args:
        job_id (str): The ID of the job to update.
        status (str | None): The new status of the job. Legacy values like
            "pending", "processing", "completed", and "failed" are supported
            and will be mapped to their new equivalents.
        stage (str | None): The new processing stage to record in the job event.
        progress (int | None): The new progress percentage (0-100) to record.
        result (dict | None): A dictionary containing the job's result data.
        error (str | None): An error message to record if the job failed.
    """
    # Map old status values to new status values
    status_mapping = {
        "pending": "queued",
        "processing": "running",
        "completed": "succeeded",
        "failed": "failed",
    }

    # Convert status if provided
    if status is not None:
        status = status_mapping.get(status, status)

    with get_db() as session:
        repo = JobRepository(session)
        repo.update_job_with_stage_progress(
            job_id=uuid.UUID(job_id),
            status=status,
            stage=stage,
            progress=progress,
            result=result,
            error=error,
        )


@dramatiq.actor(max_retries=3, min_backoff=1000, max_backoff=60000)
def process_mock(job_id: str, fail_at_stage: str | None = None) -> None:
    """
    Processes a mock job with multiple simulated stages.

    This Dramatiq actor serves as a placeholder for a real video processing
    pipeline. It simulates a multi-stage process, including "extracting",
    "analyzing", and "indexing", with configurable delays for each stage.

    The actor is designed to handle deterministic failures for testing the
    retry and error handling mechanisms of the worker. If `fail_at_stage` is
    provided, the actor will raise an exception when it reaches that stage.

    Args:
        job_id (str): The UUID of the job to process. This is used to
            update the job's status in the database.
        fail_at_stage (str | None): An optional stage name at which to
            trigger a deterministic failure. This is used for testing the
            retry mechanism.

    Raises:
        Exception: If a deterministic failure is triggered at the specified
            `fail_at_stage`. Dramatiq will catch this exception and handle
            the retry logic.
    """
    log_event("INFO", "job_started", job_id=job_id, fail_at_stage=fail_at_stage)

    try:
        # Mark job as processing
        _update_job_status(job_id, status="processing", progress=0)

        stages = ["extracting", "analyzing", "indexing"]
        total_duration = sum(STAGE_DURATIONS.values())
        elapsed = 0

        for _, stage in enumerate(stages):
            log_event("INFO", "stage_started", job_id=job_id, stage=stage)

            # Update stage
            progress = int((elapsed / total_duration) * 100)
            _update_job_status(job_id, stage=stage, progress=progress)

            # Check for deterministic failure
            if stage == fail_at_stage:
                error_msg = f"Deterministic failure at stage: {stage}"
                log_event("ERROR", "stage_failed", job_id=job_id, stage=stage, error=error_msg)
                _update_job_status(job_id, status="failed", error=error_msg)
                raise Exception(error_msg)

            # Simulate processing time
            stage_duration = STAGE_DURATIONS[stage]
            time.sleep(stage_duration)
            elapsed += stage_duration

            # Update progress
            progress = int((elapsed / total_duration) * 100)
            _update_job_status(job_id, progress=progress)

            log_event("INFO", "stage_completed", job_id=job_id, stage=stage, progress=progress)

        # Mark job as completed
        result = {
            "stages_completed": stages,
            "total_duration_seconds": elapsed,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        _update_job_status(job_id, status="completed", progress=100, result=result)
        log_event("INFO", "job_completed", job_id=job_id, result=result)

    except Exception as e:
        log_event("ERROR", "job_failed", job_id=job_id, error=str(e))
        _update_job_status(job_id, status="failed", error=str(e))
        raise
