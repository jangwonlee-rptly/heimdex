"""Job management endpoints."""

from __future__ import annotations

import os
import uuid
from typing import Any

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from redis import Redis

from heimdex_common.db import get_db
from heimdex_common.repositories import JobRepository

# Configure Dramatiq broker
redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
redis_client = Redis.from_url(redis_url)
broker = RedisBroker(url=redis_url)
dramatiq.set_broker(broker)

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobCreateRequest(BaseModel):
    """
    Defines the request model for creating a new job.

    Attributes:
        type: The type of job to create. Defaults to "mock_process".
        fail_at_stage: An optional stage name at which the job should
                       deterministically fail, for testing purposes.
    """

    type: str = "mock_process"
    fail_at_stage: str | None = None


class JobCreateResponse(BaseModel):
    """
    Defines the response model after creating a new job.

    Attributes:
        job_id: The unique identifier for the newly created job.
    """

    job_id: str


class JobStatusResponse(BaseModel):
    """
    Defines the response model for retrieving a job's status.

    Attributes:
        id: The job's unique identifier.
        status: The current status of the job (e.g., "pending", "processing",
                "completed", "failed").
        stage: The current processing stage, if applicable.
        progress: The job's progress as a percentage (0-100).
        result: A dictionary containing the job's output, if completed.
        error: An error message, if the job failed.
        created_at: The timestamp when the job was created.
        updated_at: The timestamp when the job was last updated.
    """

    id: str
    status: str
    stage: str | None
    progress: int
    result: dict[str, Any] | None
    error: str | None
    created_at: str
    updated_at: str


@router.post("", response_model=JobCreateResponse)
async def create_job(request: JobCreateRequest) -> JobCreateResponse:
    """
    Create a new job and enqueue it for background processing.

    This endpoint initiates a new job, records its initial state in the database,
    and sends a task to the Dramatiq broker for a worker to process.

    Args:
        request: A `JobCreateRequest` object containing the job type and
                 optional failure stage for testing.

    Returns:
        A `JobCreateResponse` object with the newly created job's ID.
    """
    # Default org_id for single-tenant setup
    # TODO: Replace with actual org_id from authentication when multi-tenancy is implemented
    default_org_id = uuid.UUID("00000000-0000-0000-0000-000000000000")

    # Create job using repository
    with get_db() as session:
        repo = JobRepository(session)
        job = repo.create_job(
            org_id=default_org_id,
            job_type=request.type,
            requested_by=None,  # TODO: Add from authentication context
            priority=0,
        )
        job_id = str(job.id)

    # Send task to dramatiq using message directly (avoids importing worker module)
    # This creates a message for the process_mock actor defined in heimdex_worker.tasks
    message: dramatiq.Message = dramatiq.Message(
        queue_name="default",
        actor_name="process_mock",
        args=(job_id, request.fail_at_stage),
        kwargs={},
        options={},
    )
    broker.enqueue(message)

    return JobCreateResponse(job_id=job_id)


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str) -> JobStatusResponse:
    """
    Retrieve the status of a specific job.

    This endpoint queries the database for a job by its ID and returns its current
    state, including status, progress, and any results or errors.

    Args:
        job_id: The UUID of the job to retrieve.

    Returns:
        A `JobStatusResponse` object with the job's details.

    Raises:
        HTTPException: If the job with the specified ID is not found.
    """
    with get_db() as session:
        repo = JobRepository(session)
        job = repo.get_job_by_id(uuid.UUID(job_id))

        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        # Get latest event for stage/progress/result information
        latest_event = repo.get_latest_job_event(job.id)

        # Extract stage, progress, and result from event detail
        stage = None
        progress = 0
        result = None

        if latest_event and latest_event.detail_json:
            stage = latest_event.detail_json.get("stage")
            progress = latest_event.detail_json.get("progress", 0)
            result = latest_event.detail_json.get("result")

        # Map new status values to old values for backward compatibility
        status_mapping = {
            "queued": "pending",
            "running": "processing",
            "succeeded": "completed",
            "failed": "failed",
            "canceled": "canceled",
            "dead_letter": "failed",
        }
        status = status_mapping.get(job.status, job.status)

        return JobStatusResponse(
            id=str(job.id),
            status=status,
            stage=stage,
            progress=progress,
            result=result,
            error=job.last_error_message,
            created_at=job.created_at.isoformat(),
            updated_at=job.updated_at.isoformat(),
        )
