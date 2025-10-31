"""
API Endpoints for Vector Embedding Management.

This module defines the FastAPI router for vector database operations, providing
endpoints to create and manage embeddings in Qdrant. It follows the same
transactional outbox pattern as the jobs endpoints to ensure exactly-once
delivery guarantees.

Architectural Overview:
- **Mock Embeddings**: This initial implementation provides a "hello write" endpoint
  that generates deterministic mock embeddings for testing the vector database
  integration end-to-end.
- **Tenant Isolation**: All vector operations are scoped by org_id, ensuring
  complete data isolation between organizations.
- **Idempotency**: Uses deterministic job keys based on (org_id, asset_id,
  segment_id) to prevent duplicate embedding generation.
- **Async Processing**: Embedding generation happens asynchronously via the worker
  service, allowing this endpoint to respond quickly even for expensive operations.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from heimdex_common.auth import RequestContext, verify_jwt
from heimdex_common.db import get_db
from heimdex_common.job_utils import make_job_key
from heimdex_common.models import Job, JobStatus, Outbox
from heimdex_common.repositories import JobRepository

# Create a new FastAPI router for vector-related endpoints.
# All routes in this file will be prefixed with `/vectors` and tagged as "vectors"
# in the OpenAPI documentation.
router = APIRouter(prefix="/vectors", tags=["vectors"])


class MockEmbeddingRequest(BaseModel):
    """
    Request body for creating a mock embedding job.

    This model defines the minimal information required to generate a mock
    embedding vector and store it in Qdrant. In a real-world implementation,
    this would also include parameters like the text content, embedding model,
    and other metadata.

    Attributes:
        asset_id: The unique identifier of the asset (e.g., document ID, video ID).
        segment_id: The identifier for a specific segment within the asset
            (e.g., chunk index, paragraph number, timestamp).
    """

    asset_id: str = Field(
        ..., description="The unique identifier of the asset to embed.", min_length=1
    )
    segment_id: str = Field(
        ...,
        description="The identifier for a segment within the asset (e.g., chunk_0, page_1).",
        min_length=1,
    )


class MockEmbeddingResponse(BaseModel):
    """
    Response after successfully creating a mock embedding job.

    Attributes:
        job_id: The UUID of the background job that will generate the embedding.
        asset_id: Echo of the requested asset_id for client convenience.
        segment_id: Echo of the requested segment_id for client convenience.
    """

    job_id: str
    asset_id: str
    segment_id: str


@router.post("/mock", response_model=MockEmbeddingResponse)
async def create_mock_embedding(
    request: MockEmbeddingRequest,
    ctx: Annotated[RequestContext, Depends(verify_jwt)],
) -> MockEmbeddingResponse:
    """
    Creates a job to generate a deterministic mock embedding vector.

    This endpoint implements the "Hello Write" integration test for the Qdrant
    vector database. It creates a background job that will:
    1. Generate a deterministic mock vector using numpy (seeded by the inputs)
    2. Compute a deterministic point_id using SHA256 hashing
    3. Upsert the vector to Qdrant's "embeddings" collection
    4. Mark the job as completed

    The endpoint uses the transactional outbox pattern to guarantee exactly-once
    delivery of the job message to the worker, eliminating split-brain scenarios.

    **Idempotency**: If called multiple times with the same (org_id, asset_id,
    segment_id), it will return the same job_id without creating duplicate jobs.
    The worker also uses deterministic point IDs, so upserting the same vector
    multiple times produces the same result.

    Args:
        request: The validated request body containing asset_id and segment_id.
        ctx: The authenticated request context from JWT verification, providing
            org_id and user_id.

    Returns:
        A `MockEmbeddingResponse` containing the job_id for tracking the operation.

    Example:
        POST /vectors/mock
        {
            "asset_id": "doc_123",
            "segment_id": "chunk_0"
        }

        Response:
        {
            "job_id": "550e8400-e29b-41d4-a716-446655440000",
            "asset_id": "doc_123",
            "segment_id": "chunk_0"
        }
    """
    org_id = uuid.UUID(ctx.org_id)

    # Define the payload for job_key computation
    # This determines what makes two embedding requests "the same"
    payload_for_key = {
        "asset_id": request.asset_id,
        "segment_id": request.segment_id,
        "model": "mock",
        "model_ver": "v1",
    }

    # Compute deterministic job_key for server-side idempotency
    # Same (org_id, asset_id, segment_id) -> same job_key -> same job
    job_key = make_job_key(org_id, "mock_embedding", payload_for_key)

    with get_db() as session:
        repo = JobRepository(session)

        # Check if job already exists (idempotency)
        existing_job = repo.get_job_by_job_key(job_key)
        if existing_job:
            return MockEmbeddingResponse(
                job_id=str(existing_job.id),
                asset_id=request.asset_id,
                segment_id=request.segment_id,
            )

        # Create the job first to get the ID
        job = Job(
            id=uuid.uuid4(),
            org_id=org_id,
            type="mock_embedding",
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

        # Prepare the outbox payload with the actual job_id and worker parameters
        # The mock_embedding actor expects: (job_id, org_id, asset_id, segment_id)
        outbox_payload = {
            "queue_name": "default",
            "args": (
                str(job.id),
                ctx.org_id,
                request.asset_id,
                request.segment_id,
            ),
            "kwargs": {},
            "options": {},
        }

        # Write to outbox in the same transaction
        outbox_message = Outbox(
            job_id=job.id,
            task_name="mock_embedding",
            payload=outbox_payload,
        )
        session.add(outbox_message)

        # Commit the transaction (job + event + outbox)
        session.commit()

        job_id = str(job.id)

    # The outbox dispatcher will handle publishing asynchronously
    return MockEmbeddingResponse(
        job_id=job_id,
        asset_id=request.asset_id,
        segment_id=request.segment_id,
    )
