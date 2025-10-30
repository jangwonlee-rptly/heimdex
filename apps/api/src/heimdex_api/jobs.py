"""
Job Management Endpoints.

This module defines the FastAPI router for creating and managing asynchronous
jobs. It provides endpoints for initiating new jobs and querying their status.
All job processing is deferred to a background worker service via a Dramatiq
message queue.

The API handles:
-   Creating a new job record in the database.
-   Enqueuing a task for the worker to process the job.
-   Retrieving the current status of a job.
"""

from __future__ import annotations

import os
import uuid
from typing import Annotated, Any

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from redis import Redis

from heimdex_common.auth import RequestContext, verify_jwt
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

    This Pydantic model is used to validate the request body for the `create_job`
    endpoint. It specifies the expected data structure for initiating a new
    background job.

    Attributes:
        type (str): The type of job to create, which determines the actor
            that will be executed by the worker. Defaults to "mock_process".
        fail_at_stage (str | None): An optional stage name at which the job
            should deterministically fail. This is used for testing the
            worker's retry and error handling mechanisms. If None, the job
            is expected to complete successfully.
    """

    type: str = "mock_process"
    fail_at_stage: str | None = None


class JobCreateResponse(BaseModel):
    """
    Defines the response model after creating a new job.

    This Pydantic model is used to serialize the response for the `create_job`
    endpoint. It provides a standardized structure for returning the ID of the
    newly created job.

    Attributes:
        job_id (str): The unique identifier (UUID) for the newly created job.
            This ID can be used to query the job's status.
    """

    job_id: str


class JobStatusResponse(BaseModel):
    """
    Defines the response model for retrieving a job's status.

    This Pydantic model is used to serialize the response for the `get_job_status`
    endpoint. It provides a comprehensive overview of a job's current state,
    including its progress, result, and any errors.

    Attributes:
        id (str): The job's unique identifier (UUID).
        status (str): The current status of the job. Common values include
            "pending", "processing", "completed", and "failed".
        stage (str | None): The current processing stage, if the job is running
            and reports its progress in stages.
        progress (int): The job's progress as a percentage, from 0 to 100.
        result (dict[str, Any] | None): A dictionary containing the job's
            output if it has completed successfully.
        error (str | None): An error message if the job has failed.
        created_at (str): The ISO 8601 timestamp of when the job was created.
        updated_at (str): The ISO 8601 timestamp of when the job was last updated.
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
async def create_job(
    request: JobCreateRequest,
    ctx: Annotated[RequestContext, Depends(verify_jwt)],
) -> JobCreateResponse:
    """
    Creates and enqueues a new job for asynchronous processing.

    This endpoint serves as the primary entrypoint for initiating background
    tasks. It performs several key actions:
    1.  It creates a new job record in the database with an initial 'queued'
        status, using the `JobRepository`. The job is automatically scoped
        to the authenticated user's organization.
    2.  It constructs a `dramatiq.Message` to be consumed by a background
        worker. This message contains the job ID and any parameters required
        by the worker task.
    3.  It enqueues the message using the configured Dramatiq broker, making
        it available for a worker to pick up.

    The job is automatically associated with the requesting user's organization,
    ensuring tenant isolation. Only users from the same organization will be
    able to query this job's status.

    Args:
        request (JobCreateRequest): The request body containing the details
            for the job to be created. This includes the `type` of the job
            and an optional `fail_at_stage` parameter for testing purposes.
        ctx (RequestContext): Authenticated request context containing user
            and organization identity (injected via JWT verification).

    Returns:
        JobCreateResponse: A response object containing the unique identifier
            (`job_id`) of the newly created and enqueued job.
    """
    # Create job using repository with authenticated org_id
    with get_db() as session:
        repo = JobRepository(session)
        job = repo.create_job(
            org_id=uuid.UUID(ctx.org_id),
            job_type=request.type,
            requested_by=ctx.user_id,
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
async def get_job_status(
    job_id: str,
    ctx: Annotated[RequestContext, Depends(verify_jwt)],
) -> JobStatusResponse:
    """
    Retrieves the current status and details of a specific job.

    This endpoint queries the database for a job by its unique identifier and
    returns a comprehensive overview of its current state. This includes its
    status, progress, stage, and any results or errors.

    The endpoint enforces tenant isolation: users can only query jobs belonging
    to their organization. Attempting to access a job from another organization
    returns a 403 Forbidden error.

    The status mapping logic ensures that the job status values from the new
    `JobStatus` enum are backward-compatible with older clients.

    Args:
        job_id (str): The UUID of the job to retrieve, passed as a path
            parameter.
        ctx (RequestContext): Authenticated request context containing user
            and organization identity (injected via JWT verification).

    Returns:
        JobStatusResponse: A response object containing the detailed status
            of the job.

    Raises:
        HTTPException: A 404 Not Found error is raised if no job with the
            specified `job_id` is found in the database.
        HTTPException: A 403 Forbidden error is raised if the job belongs
            to a different organization than the authenticated user.
    """
    with get_db() as session:
        repo = JobRepository(session)
        job = repo.get_job_by_id(uuid.UUID(job_id))

        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        # Enforce tenant isolation: only allow access to jobs in the same org
        if str(job.org_id) != ctx.org_id:
            raise HTTPException(
                status_code=403,
                detail="Access denied: job belongs to a different organization",
            )

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
        raw_status = job.status.value if hasattr(job.status, "value") else job.status
        status = status_mapping.get(raw_status, raw_status)

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
