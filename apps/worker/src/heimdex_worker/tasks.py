"""Dramatiq tasks for background job processing."""

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
    Update a job's status in the database.

    This function uses the JobRepository to update job status with SQLAlchemy ORM.
    It maintains backward compatibility with the old function signature while storing
    stage, progress, and result in the job_event table.

    Args:
        job_id: The ID of the job to update.
        status: The new status of the job (old values: pending/processing/completed/failed).
        stage: The new processing stage (stored in event detail).
        progress: The new progress percentage (stored in event detail).
        result: A dictionary containing the job's result (stored in event detail).
        error: An error message if the job failed.
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
    Process a mock job with multiple simulated stages.

    This Dramatiq actor simulates a multi-stage pipeline (extracting, analyzing,
    indexing) and updates the job's status in the database at each step. It is
    designed to handle deterministic failures for testing purposes.

    Args:
        job_id: The UUID of the job to process.
        fail_at_stage: An optional stage name at which to trigger a
                       deterministic failure for testing the retry mechanism.

    Raises:
        Exception: If a deterministic failure is triggered.
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
