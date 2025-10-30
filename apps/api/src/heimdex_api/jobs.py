"""
API Endpoints for Asynchronous Job Management.

This module defines the FastAPI router that exposes endpoints for creating and
monitoring asynchronous background jobs. It acts as the primary interface for
clients to submit long-running tasks to the Heimdex platform.

Architectural Overview:
- **Decoupling**: This API's core responsibility is to accept job requests,
  validate them, create a persistent record in the database, and enqueue a
  message for a background worker. It is completely decoupled from the actual
  implementation of the job processing logic, which resides in the `worker`
  service.
- **Message Queueing**: It uses Dramatiq with a Redis broker to send tasks to
  the worker. This provides a reliable, asynchronous communication channel that
  can handle backpressure and ensures that jobs are not lost if the worker is
  temporarily unavailable.
- **Tenant Isolation**: All endpoints are protected by JWT authentication and
  enforce strict tenant isolation. A user can only create or view jobs that
  belong to their own organization.
"""

from __future__ import annotations

import os
import uuid
from typing import Annotated, Any

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from redis import Redis

from heimdex_common.auth import RequestContext, verify_jwt
from heimdex_common.db import get_db
from heimdex_common.repositories import JobRepository

# --- Dramatiq Broker Setup ---
# This section configures the connection to the Redis message broker that
# Dramatiq uses to enqueue and dequeue tasks. The API service acts as a
# "producer," sending messages, while the worker service acts as a "consumer."
redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
redis_client = Redis.from_url(redis_url)
broker = RedisBroker(url=redis_url)
dramatiq.set_broker(broker)

# Create a new FastAPI router for job-related endpoints.
# All routes in this file will be prefixed with `/jobs` and tagged as "jobs"
# in the OpenAPI documentation.
router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobCreateRequest(BaseModel):
    """
    Defines the JSON request body for creating a new asynchronous job.

    This Pydantic model provides data validation for the `POST /jobs` endpoint.
    It specifies the parameters a client can provide to initiate a new task.

    Attributes:
        type: A string that identifies the type of job to be executed. This
              acts as a routing key, determining which worker function (actor)
              will process the job.
        fail_at_stage: A special parameter used for testing. If provided, it
                       instructs the mock worker to simulate a failure at a
                       specific stage, allowing developers to test the retry
                       and error handling mechanisms of the system.
    """

    type: str = Field(default="mock_process", description="The type of job to create.")
    fail_at_stage: str | None = Field(
        default=None,
        description="For testing: stage at which the job should deterministically fail.",
    )


class JobCreateResponse(BaseModel):
    """
    Defines the JSON response body after successfully creating a job.

    This model ensures a consistent response format, providing the client with
    the essential information they need to track the newly created job.

    Attributes:
        job_id: The globally unique identifier (UUID) for the created job. The
                client can use this ID with the `GET /jobs/{job_id}` endpoint
                to poll for the job's status.
    """

    job_id: str


class JobStatusResponse(BaseModel):
    """
    Defines the JSON response for a job status query.

    This model provides a comprehensive, client-facing view of a job's state.
    It consolidates information from the `Job` record and its most recent
    `JobEvent` to give a full picture of the job's progress.

    Attributes:
        id: The job's unique identifier.
        status: The current status of the job (e.g., "pending", "processing",
                "completed", "failed").
        stage: The current processing stage, if reported by the worker.
        progress: A numerical representation of the job's progress (0-100).
        result: The output or result of the job, if it completed successfully.
        error: A descriptive error message, if the job failed.
        created_at: The ISO 8601 timestamp of when the job was created.
        updated_at: The ISO 8601 timestamp of the last update.
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
    Creates a new job record and enqueues it for background processing.

    This endpoint orchestrates the two main steps of starting a job:
    1.  **Persistence**: It uses the `JobRepository` to create a new `Job` row
        in the database. This record acts as the durable source of truth for
        the job's state. The job is immediately associated with the authenticated
        user's organization (`ctx.org_id`).
    2.  **Enqueuing**: It constructs and sends a `dramatiq.Message` to the Redis
        broker. This message contains the `job_id` and any other parameters
        the worker needs to perform the task.

    By creating the database record *before* enqueuing the task, we ensure that
    even if the worker picks up the job instantly, a corresponding record will
    be there to update.

    Args:
        request: The validated request body.
        ctx: The authenticated request context, injected by the `verify_jwt`
             dependency.

    Returns:
        A `JobCreateResponse` containing the new job's UUID.
    """
    with get_db() as session:
        repo = JobRepository(session)
        job = repo.create_job(
            org_id=uuid.UUID(ctx.org_id),
            job_type=request.type,
            requested_by=ctx.user_id,
        )
        job_id = str(job.id)

    # We manually construct a Dramatiq message here. This is a deliberate
    # choice to avoid a direct import dependency from the `api` service to the
    # `worker` service. This maintains the decoupling between the two services.
    message: dramatiq.Message = dramatiq.Message(
        queue_name="default",
        actor_name="process_mock",  # The name of the function the worker should call
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
    Retrieves the current status and detailed progress of a specific job.

    This endpoint provides clients with a way to poll for the status of a job
    they have created.

    **Tenant Isolation Enforcement**: A critical security feature of this
    endpoint is that it checks if the `org_id` of the requested job matches
    the `org_id` from the user's authentication token (`ctx`). If they do not
    match, it returns a 403 Forbidden error, preventing users from one
    organization from viewing data belonging to another.

    Args:
        job_id: The UUID of the job to retrieve.
        ctx: The authenticated request context.

    Returns:
        A `JobStatusResponse` with the full details of the job.

    Raises:
        HTTPException(404): If a job with the given ID is not found.
        HTTPException(403): If the user is not authorized to view the job.
    """
    with get_db() as session:
        repo = JobRepository(session)
        job = repo.get_job_by_id(uuid.UUID(job_id))

        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        if str(job.org_id) != ctx.org_id:
            raise HTTPException(status_code=403, detail="Access denied")

        latest_event = repo.get_latest_job_event(job.id)
        details = latest_event.detail_json if latest_event and latest_event.detail_json else {}

        # Backward-compatible status mapping for older clients
        status_mapping = {
            "queued": "pending",
            "running": "processing",
            "succeeded": "completed",
            "failed": "failed",
            "canceled": "canceled",
            "dead_letter": "failed",
        }
        status = status_mapping.get(job.status.value, job.status.value)

        return JobStatusResponse(
            id=str(job.id),
            status=status,
            stage=details.get("stage"),
            progress=details.get("progress", 0),
            result=details.get("result"),
            error=job.last_error_message,
            created_at=job.created_at.isoformat(),
            updated_at=job.updated_at.isoformat(),
        )
