"""Job management endpoints."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from typing import Any

import dramatiq
import psycopg2.extras
from dramatiq.brokers.redis import RedisBroker
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from redis import Redis

from heimdex_common.db import get_db

# Configure Dramatiq broker
redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
redis_client = Redis.from_url(redis_url)
broker = RedisBroker(url=redis_url)
dramatiq.set_broker(broker)

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobCreateRequest(BaseModel):
    """Request to create a new job."""

    type: str = "mock_process"
    fail_at_stage: str | None = None


class JobCreateResponse(BaseModel):
    """Response from creating a job."""

    job_id: str


class JobStatusResponse(BaseModel):
    """Job status response."""

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
    """Create a new job and enqueue it for processing."""
    job_id = str(uuid.uuid4())

    # Insert job into database
    with get_db() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO jobs (id, status, stage, progress, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (job_id, "pending", None, 0, datetime.now(UTC), datetime.now(UTC)),
        )

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
    """Get the status of a job."""
    with get_db() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id, status, stage, progress, result, error, created_at, updated_at
            FROM jobs
            WHERE id = %s
            """,
            (job_id,),
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobStatusResponse(
        id=str(row["id"]),
        status=row["status"],
        stage=row["stage"],
        progress=row["progress"],
        result=row["result"],
        error=row["error"],
        created_at=row["created_at"].isoformat(),
        updated_at=row["updated_at"].isoformat(),
    )
