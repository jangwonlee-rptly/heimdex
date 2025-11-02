"""
API Endpoints for Vector Embedding Management.

This module defines the FastAPI router for vector database operations, providing
endpoints to create and manage embeddings in Qdrant. It follows the same
transactional outbox pattern as the jobs endpoints to ensure exactly-once
delivery guarantees.

Architectural Overview:
- **Mock Embeddings**: Provides a "hello write" endpoint for testing
- **Production Embeddings**: Real ML-powered embedding generation via /vectors/embed
- **Semantic Search**: Query-time inference and vector search via /vectors/search
- **Tenant Isolation**: All vector operations are scoped by org_id
- **Idempotency**: Uses deterministic job keys with text_hash for deduplication
- **Async Processing**: Embedding generation happens asynchronously via worker service
- **PII Minimization**: Raw text never stored in Qdrant, only metadata
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from qdrant_client.models import FieldCondition, Filter, MatchValue

from heimdex_common.auth import RequestContext, verify_jwt
from heimdex_common.db import get_db
from heimdex_common.embeddings import get_adapter
from heimdex_common.job_utils import make_job_key
from heimdex_common.models import Job, JobStatus, Outbox
from heimdex_common.repositories import JobRepository
from heimdex_common.vector.qdrant_repo import client as get_qdrant_client

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


# --- Production Endpoints ---


class EmbedTextRequest(BaseModel):
    """
    Request body for creating a real text embedding job.

    This model defines the parameters for generating production embeddings using
    real ML models (SentenceTransformers). The text will be embedded asynchronously
    by the worker service.

    Attributes:
        asset_id: The unique identifier of the asset (e.g., document ID).
        segment_id: The identifier for a specific segment within the asset (e.g., chunk_0).
        text: The raw text content to embed (PII-sensitive, not stored in Qdrant).
        model: Optional model name override (defaults to EMBEDDING_MODEL_NAME env var).
        model_ver: Optional model version tag for tracking (e.g., "v1").
    """

    asset_id: str = Field(..., description="Unique identifier of the asset", min_length=1)
    segment_id: str = Field(
        ..., description="Segment identifier within the asset (e.g., chunk_0)", min_length=1
    )
    text: str = Field(
        ..., description="Raw text content to embed (not stored in Qdrant)", min_length=1
    )
    model: str | None = Field(
        None, description="Optional model name override (e.g., 'minilm-l6-v2')"
    )
    model_ver: str | None = Field(None, description="Optional model version tag (e.g., 'v1')")


class EmbedTextResponse(BaseModel):
    """
    Response after successfully creating a text embedding job.

    Attributes:
        job_id: The UUID of the background job that will generate the embedding.
        asset_id: Echo of the requested asset_id for client convenience.
        segment_id: Echo of the requested segment_id for client convenience.
    """

    job_id: str
    asset_id: str
    segment_id: str


def _compute_text_hash(text: str) -> str:
    """Compute SHA256 hash of text for job deduplication."""
    hash_obj = hashlib.sha256(text.encode("utf-8"))
    return hash_obj.hexdigest()[:16]  # First 16 chars (64 bits)


@router.post("/embed", response_model=EmbedTextResponse)
async def embed_text(
    request: EmbedTextRequest,
    ctx: Annotated[RequestContext, Depends(verify_jwt)],
) -> EmbedTextResponse:
    """
    Creates a job to generate a real text embedding using ML models.

    This is the production endpoint for embedding generation. It enqueues a job
    that will:
    1. Load the configured embedding model (SentenceTransformers by default)
    2. Truncate text if exceeds model's max_seq_len
    3. Generate the embedding vector
    4. Upsert the vector to Qdrant with PII-minimized payload
    5. Mark the job as completed

    **Idempotency**: The job_key includes text_hash, so submitting the same text
    for the same (org_id, asset_id, segment_id) will return the existing job_id
    without creating duplicate jobs. However, the point_id does NOT include
    text_hash, so updating the text for the same segment will overwrite the
    previous vector (latest-wins semantics).

    **PII Minimization**: The raw text is temporarily stored in the Outbox table
    (deleted after dispatch) but NEVER stored in Qdrant. Only metadata (text_len,
    truncated_len, model, etc.) is stored in the vector payload.

    Args:
        request: The validated request body containing asset_id, segment_id, and text.
        ctx: The authenticated request context from JWT verification.

    Returns:
        An `EmbedTextResponse` containing the job_id for tracking the operation.

    Example:
        POST /vectors/embed
        {
            "asset_id": "doc_123",
            "segment_id": "chunk_0",
            "text": "The quick brown fox jumps over the lazy dog.",
            "model": "minilm-l6-v2",
            "model_ver": "v1"
        }

        Response:
        {
            "job_id": "550e8400-e29b-41d4-a716-446655440000",
            "asset_id": "doc_123",
            "segment_id": "chunk_0"
        }
    """
    org_id = uuid.UUID(ctx.org_id)

    # Compute text_hash for job deduplication
    # This ensures same text for same segment = same job
    text_hash = _compute_text_hash(request.text)

    # Define the payload for job_key computation
    # CRITICAL: Includes text_hash for deduplication
    payload_for_key = {
        "asset_id": request.asset_id,
        "segment_id": request.segment_id,
        "text_hash": text_hash,
        "model": request.model or "default",
        "model_ver": request.model_ver or "v1",
    }

    # Compute deterministic job_key for server-side idempotency
    job_key = make_job_key(org_id, "dispatch_embed_text", payload_for_key)

    with get_db() as session:
        repo = JobRepository(session)

        # Check if job already exists (idempotency)
        existing_job = repo.get_job_by_job_key(job_key)
        if existing_job:
            return EmbedTextResponse(
                job_id=str(existing_job.id),
                asset_id=request.asset_id,
                segment_id=request.segment_id,
            )

        # Create the job first to get the ID
        job = Job(
            id=uuid.uuid4(),
            org_id=org_id,
            type="dispatch_embed_text",
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

        # Prepare the outbox payload
        # IMPORTANT: Actor signature is dispatch_embed_text(job_id: str, *, org_id, asset_id, ...)
        # So we use positional args for job_id, and kwargs for everything else
        outbox_payload = {
            "queue_name": "default",
            "args": (str(job.id),),  # Only job_id is positional
            "kwargs": {
                "org_id": ctx.org_id,
                "asset_id": request.asset_id,
                "segment_id": request.segment_id,
                "text": request.text,  # Temporarily in outbox, not in Qdrant
                "model": request.model,
                "model_ver": request.model_ver,
            },
            "options": {},
        }

        # Write to outbox in the same transaction
        outbox_message = Outbox(
            job_id=job.id,
            task_name="dispatch_embed_text",
            payload=outbox_payload,
        )
        session.add(outbox_message)

        # Commit the transaction (job + event + outbox)
        session.commit()

        job_id = str(job.id)

    # The outbox dispatcher will handle publishing asynchronously
    return EmbedTextResponse(
        job_id=job_id,
        asset_id=request.asset_id,
        segment_id=request.segment_id,
    )


class SearchVectorsRequest(BaseModel):
    """
    Request body for semantic search using text query.

    This model defines the parameters for performing semantic search in the vector
    database. The query text is embedded on-the-fly (no job creation), and the
    resulting vector is used to find similar vectors in Qdrant.

    Attributes:
        query_text: The text query to embed and search for.
        limit: Maximum number of results to return (default: 10, max: 100).
        asset_id: Optional filter to only search within a specific asset.
        segment_id: Optional filter to only search within a specific segment.
    """

    query_text: str = Field(..., description="Text query to embed and search", min_length=1)
    limit: int = Field(10, description="Maximum number of results", ge=1, le=100)
    asset_id: str | None = Field(None, description="Optional filter by asset_id")
    segment_id: str | None = Field(None, description="Optional filter by segment_id")


class SearchVectorsResult(BaseModel):
    """
    A single search result from vector search.

    Attributes:
        point_id: The Qdrant point ID of the matching vector.
        score: The similarity score (0.0 to 1.0 for cosine similarity).
        payload: The metadata payload stored with the vector.
    """

    point_id: str
    score: float
    payload: dict[str, Any]


class SearchVectorsResponse(BaseModel):
    """
    Response from semantic search endpoint.

    Attributes:
        results: List of search results, ordered by descending score.
        query_model: The embedding model used to embed the query.
        query_model_ver: The version of the embedding model.
        total: Total number of results returned.
    """

    results: list[SearchVectorsResult]
    query_model: str
    query_model_ver: str
    total: int


@router.post("/search", response_model=SearchVectorsResponse)
async def search_vectors(
    request: SearchVectorsRequest,
    ctx: Annotated[RequestContext, Depends(verify_jwt)],
) -> SearchVectorsResponse:
    """
    Performs semantic search using query-time inference.

    This endpoint embeds the query text on-the-fly (no job creation) and performs
    a semantic search in the Qdrant vector database. It supports filtering by
    asset_id and segment_id for scoped searches.

    **Query-Time Inference**: Unlike /vectors/embed, this endpoint does NOT create
    a job. It immediately embeds the query text and searches for similar vectors.
    This provides fast, interactive search results.

    **Tenant Isolation**: Results are automatically filtered by org_id (from JWT)
    to ensure users only see vectors from their organization.

    **Filtering**: Simple server-side filters allow searching within specific assets
    or segments. Filters are combined with AND logic.

    Args:
        request: The validated request body containing query_text and optional filters.
        ctx: The authenticated request context from JWT verification.

    Returns:
        A `SearchVectorsResponse` containing the search results with scores and payloads.

    Raises:
        HTTPException: 400 if query text is empty, 500 if search fails.

    Example:
        POST /vectors/search
        {
            "query_text": "machine learning algorithms",
            "limit": 5,
            "asset_id": "doc_123"
        }

        Response:
        {
            "results": [
                {
                    "point_id": "abc123...",
                    "score": 0.95,
                    "payload": {
                        "org_id": "...",
                        "asset_id": "doc_123",
                        "segment_id": "chunk_0",
                        "model": "minilm-l6-v2",
                        "text_len": 42
                    }
                },
                ...
            ],
            "query_model": "sentence-transformers/all-MiniLM-L6-v2",
            "query_model_ver": "v1",
            "total": 5
        }
    """
    # Validate query text
    if not request.query_text or not request.query_text.strip():
        raise HTTPException(status_code=400, detail="query_text cannot be empty")

    try:
        # Load embedding adapter (singleton, cached)
        adapter = get_adapter()

        # Embed query text (query-time inference, no job)
        query_vector = adapter.embed(request.query_text)

        # Get Qdrant client
        collection_name = "embeddings"
        client = get_qdrant_client()

        # Build filters (all filters are AND-ed together)
        # CRITICAL: Always filter by org_id for tenant isolation
        filter_conditions = [FieldCondition(key="org_id", match=MatchValue(value=ctx.org_id))]

        if request.asset_id:
            filter_conditions.append(
                FieldCondition(key="asset_id", match=MatchValue(value=request.asset_id))
            )

        if request.segment_id:
            filter_conditions.append(
                FieldCondition(key="segment_id", match=MatchValue(value=request.segment_id))
            )

        query_filter = Filter(must=filter_conditions)

        # Perform vector search
        search_results = client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            query_filter=query_filter,
            limit=request.limit,
        )

        # Format results
        results = [
            SearchVectorsResult(
                point_id=str(hit.id),
                score=hit.score,
                payload=hit.payload or {},
            )
            for hit in search_results
        ]

        return SearchVectorsResponse(
            results=results,
            query_model=adapter.name,
            query_model_ver="v1",  # TODO: Make this configurable
            total=len(results),
        )

    except ValueError as e:
        # Validation error from adapter.embed()
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        # Unexpected error during search
        raise HTTPException(status_code=500, detail=f"Search failed: {e!s}") from e
