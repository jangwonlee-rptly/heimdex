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
from heimdex_common.job_utils import make_job_key
from heimdex_common.models import Job, JobStatus, Outbox
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
    Creates a new job with transactional outbox pattern for exactly-once delivery.

    This endpoint implements the transactional outbox pattern to guarantee
    exactly-once message delivery semantics. The critical improvement over the
    previous implementation is that both the job record AND the outbox message
    are written in a single atomic database transaction.

    Workflow:
    1.  Compute a deterministic job_key from org_id, job_type, and payload
    2.  Check if a job with this key already exists (idempotency)
    3.  Within a single transaction:
        a. Create the Job record in QUEUED state
        b. Create a JobEvent for ENQUEUED
        c. Create an Outbox record with the Dramatiq message payload
    4.  Commit the transaction
    5.  The outbox dispatcher (running in a background thread) will later:
        a. Read unsent outbox messages
        b. Publish them to Dramatiq
        c. Mark them as sent

    This eliminates the split-brain risk where a job could exist in the database
    but never be published to the queue, or vice versa.

    Args:
        request: The validated request body.
        ctx: The authenticated request context from JWT verification.

    Returns:
        A `JobCreateResponse` containing the job UUID (new or existing).
    """
    org_id = uuid.UUID(ctx.org_id)

    # Define the payload subset used for job_key computation
    # Only include fields that affect idempotency (not transient fields)
    payload_for_key = {
        "type": request.type,
        # For mock jobs, fail_at_stage doesn't affect idempotency
        # For real jobs, include stable identifiers like video_id, file_path, etc.
    }

    # Compute deterministic job_key for server-side idempotency
    job_key = make_job_key(org_id, request.type, payload_for_key)

    with get_db() as session:
        repo = JobRepository(session)

        # Check if job already exists (idempotency check happens in repository)
        existing_job = repo.get_job_by_job_key(job_key)
        if existing_job:
            return JobCreateResponse(job_id=str(existing_job.id))

        # Create the job first to get the ID
        job = Job(
            id=uuid.uuid4(),
            org_id=org_id,
            type=request.type,
            status=JobStatus.QUEUED,
            job_key=job_key,
            requested_by=ctx.user_id,
        )
        session.add(job)
        session.flush()  # Get the job.id

        # Log the initial event
        repo.log_job_event(
            job_id=job.id,
            prev_status=None,
            next_status=JobStatus.QUEUED.value,
        )

        # NOW prepare the outbox payload with the actual job_id
        outbox_payload = {
            "queue_name": "default",
            "args": (str(job.id), request.fail_at_stage),
            "kwargs": {},
            "options": {},
        }

        # Write to outbox in the same transaction
        outbox_message = Outbox(
            job_id=job.id,
            task_name="process_mock",
            payload=outbox_payload,
        )
        session.add(outbox_message)

        # Commit the transaction (job + event + outbox)
        session.commit()

        job_id = str(job.id)

    # DO NOT call broker.enqueue() here!
    # The outbox dispatcher will handle publishing asynchronously.

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
