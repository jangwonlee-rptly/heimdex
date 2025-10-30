"""
Dramatiq Actors for Asynchronous Background Job Processing.

This module is the core of the worker service. It defines the "actors," which are
the functions that perform the actual background processing. These functions are
decorated with `@dramatiq.actor`, which registers them with the Dramatiq broker
so they can be called by messages from the queue.

Architectural Role:
- **Consumer**: This module acts as the "consumer" in the producer-consumer
  pattern. The API service produces messages, and the actors in this module
  consume them.
- **Business Logic**: The primary business logic of a background task (e.g.,
  video transcoding, data analysis) resides within these actor functions.
- **State Management**: A crucial responsibility of each actor is to report the
  progress and final status of a job back to the central database using the
  `JobRepository`. This ensures that the job's state is always visible to the
  rest of the system via the API.
"""

from __future__ import annotations

import os
import time
import uuid
from datetime import UTC, datetime

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from heimdex_common.db import get_db
from heimdex_common.models import JobStatus
from heimdex_common.repositories import JobRepository

from .logger import log_event

# --- Dramatiq Broker and Actor Configuration ---
redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
broker = RedisBroker(url=redis_url)
dramatiq.set_broker(broker)

# --- Mock Processing Configuration ---
STAGE_DURATIONS = {"extracting": 2, "analyzing": 3, "indexing": 1}


def _update_job_status(
    job_id: str,
    status: JobStatus | None = None,
    stage: str | None = None,
    progress: int | None = None,
    result: dict | None = None,
    error: str | None = None,
) -> None:
    """
    A centralized helper function for updating a job's status in the database.

    This function provides a consistent, transactional way for actors to report
    their progress. It encapsulates the interaction with the `JobRepository`,
    ensuring that every status update is a clean, atomic operation.

    Args:
        job_id: The UUID of the job to update.
        status: The new `JobStatus` of the job.
        stage: The current processing stage to be recorded in a `JobEvent`.
        progress: The current progress percentage (0-100).
        result: The final result of the job, to be stored in a `JobEvent`.
        error: An error message to be stored if the job failed.
    """
    with get_db() as session:
        repo = JobRepository(session)

        # If we have result or error, use update_job_status with event_detail
        if result is not None or error is not None:
            event_detail: dict = {}
            if stage is not None:
                event_detail["stage"] = stage
            if progress is not None:
                event_detail["progress"] = progress
            if result is not None:
                event_detail["result"] = result

            if status:
                repo.update_job_status(
                    job_id=uuid.UUID(job_id),
                    status=status,
                    last_error_message=error,
                    log_event=True,
                    event_detail=event_detail if event_detail else None,
                )
        # Otherwise, use update_job_with_stage_progress for stage/progress updates
        elif stage is not None and progress is not None:
            repo.update_job_with_stage_progress(
                job_id=uuid.UUID(job_id),
                stage=stage,
                progress=progress,
                status=status,
            )
        # Status-only update
        elif status is not None:
            repo.update_job_status(
                job_id=uuid.UUID(job_id),
                status=status,
                last_error_message=error,
                log_event=True,
            )


@dramatiq.actor(
    # The actor's name must match the `actor_name` used in the API service
    # when the message was created.
    actor_name="process_mock",
    # Configure Dramatiq's automatic retry mechanism. If this actor raises an
    # exception, Dramatiq will re-enqueue it up to 3 times.
    max_retries=3,
    # Use an exponential backoff strategy for retries, starting with a 1-second
    # delay and capped at a 60-second delay. This prevents a failing job from
    # overwhelming the system with rapid retries.
    min_backoff=1000,
    max_backoff=60000,
)
def process_mock(job_id: str, fail_at_stage: str | None = None) -> None:
    """
    A Dramatiq actor that simulates a multi-stage background job with idempotency.

    This function is idempotent and re-entrant, following the requirement for
    at-least-once delivery semantics. If Dramatiq delivers the same message
    multiple times (due to retries or other reasons), this function will:
    1. Check if the job is already in a terminal state
    2. If yes, no-op and return immediately (idempotent)
    3. If no, proceed with processing

    Key responsibilities:
    1.  **Idempotency Check**: Verify job is not already complete
    2.  Marking the job as `RUNNING` when it starts
    3.  Periodically updating the job's progress and current stage
    4.  Handling potential failures and allowing Dramatiq's retry logic to take over
    5.  Marking the job as `SUCCEEDED` upon successful completion
    6.  Marking the job as `FAILED` if a non-transient error occurs

    Args:
        job_id: The UUID of the job to process, passed from the enqueued message.
        fail_at_stage: An optional parameter to force a failure at a specific
                       stage, used for testing the resilience of the system.

    Raises:
        Exception: If a deterministic failure is triggered, this exception will
                   be caught by Dramatiq, which will then schedule a retry
                   according to the actor's configuration.
    """
    log_event("INFO", "job_processing_started", job_id=job_id, fail_at_stage=fail_at_stage)

    # CRITICAL IDEMPOTENCY CHECK: Verify the job is not already in a terminal state
    # This prevents double-processing if Dramatiq delivers the message multiple times
    with get_db() as session:
        repo = JobRepository(session)
        job = repo.get_job_by_id(uuid.UUID(job_id))

        if not job:
            log_event("ERROR", "job_not_found", job_id=job_id)
            return  # Job doesn't exist, nothing to do

        # Terminal states: job is already done, no-op to maintain idempotency
        terminal_states = {
            JobStatus.SUCCEEDED,
            JobStatus.FAILED,
            JobStatus.CANCELED,
            JobStatus.DEAD_LETTER,
        }
        if job.status in terminal_states:
            log_event(
                "INFO",
                "job_already_terminal",
                job_id=job_id,
                status=job.status.value,
                message="Idempotent no-op: job already in terminal state",
            )
            return  # Idempotent return: job already processed

    # Proceed with processing only if job is not terminal
    try:
        _update_job_status(job_id, status=JobStatus.RUNNING, progress=0, stage="starting")

        stages = list(STAGE_DURATIONS.keys())
        total_duration = sum(STAGE_DURATIONS.values())
        elapsed_time = 0

        for stage in stages:
            log_event("INFO", "stage_started", job_id=job_id, stage=stage)
            progress = int((elapsed_time / total_duration) * 100)
            _update_job_status(job_id, stage=stage, progress=progress)

            if stage == fail_at_stage:
                error_msg = f"Deterministic failure at stage: {stage}"
                log_event(
                    "ERROR", "deterministic_failure", job_id=job_id, stage=stage, error=error_msg
                )
                # Before raising the exception, update the status to FAILED.
                # This provides immediate feedback via the API. When Dramatiq
                # retries, the status will be updated back to RUNNING.
                _update_job_status(job_id, status=JobStatus.FAILED, error=error_msg)
                raise Exception(error_msg)

            time.sleep(STAGE_DURATIONS[stage])
            elapsed_time += STAGE_DURATIONS[stage]
            log_event("INFO", "stage_completed", job_id=job_id, stage=stage)

        # Mark job as completed successfully
        result = {
            "stages_completed": stages,
            "total_duration_seconds": elapsed_time,
            "completed_at": datetime.now(UTC).isoformat(),
        }
        _update_job_status(
            job_id, status=JobStatus.SUCCEEDED, progress=100, result=result, stage="finished"
        )
        log_event("INFO", "job_processing_succeeded", job_id=job_id)

    except Exception as e:
        # This is a catch-all for unexpected errors. We log the error and
        # update the job's status to FAILED. Then, we re-raise the exception
        # to let Dramatiq handle the retry logic.
        log_event("ERROR", "job_processing_failed", job_id=job_id, error=str(e))
        _update_job_status(job_id, status=JobStatus.FAILED, error=str(e), stage="error")
        raise
