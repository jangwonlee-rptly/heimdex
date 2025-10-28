"""Dramatiq tasks for background job processing."""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from typing import Any

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from heimdex_common.db import get_db

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
    """Update job status in database."""
    with get_db() as conn, conn.cursor() as cur:
        updates = ["updated_at = %s"]
        values: list[Any] = [datetime.now(UTC)]

        if status is not None:
            updates.append("status = %s")
            values.append(status)
        if stage is not None:
            updates.append("stage = %s")
            values.append(stage)
        if progress is not None:
            updates.append("progress = %s")
            values.append(progress)
        if result is not None:
            updates.append("result = %s::jsonb")
            import json

            values.append(json.dumps(result))
        if error is not None:
            updates.append("error = %s")
            values.append(error)

        values.append(job_id)
        cur.execute(
            f"UPDATE jobs SET {', '.join(updates)} WHERE id = %s",
            tuple(values),
        )


@dramatiq.actor(max_retries=3, min_backoff=1000, max_backoff=60000)
def process_mock(job_id: str, fail_at_stage: str | None = None) -> None:
    """
    Mock multi-stage job processing.

    Simulates a video processing pipeline with three stages:
    1. extracting (2 sec) - simulates frame extraction
    2. analyzing (3 sec) - simulates scene detection
    3. indexing (1 sec) - simulates vector generation

    Args:
        job_id: UUID of the job to process
        fail_at_stage: Optional stage name to trigger deterministic failure for testing
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
