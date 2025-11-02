"""
Dramatiq Actor for Real Text Embedding Generation.

This module implements the production embedding pipeline using real ML models
(SentenceTransformers) instead of mock vectors. It handles text truncation,
PII minimization, and proper metadata tracking.

Key Features:
- **Real Embeddings**: Uses SentenceTransformers models via the adapter pattern
- **PII Minimization**: Never stores raw text in Qdrant, only metadata (lengths, hashes)
- **Idempotency**: Terminal-state guard + deterministic point IDs (no text_hash in point_id)
- **Deduplication**: job_key includes text_hash (enforced at API level)
- **Truncation Handling**: Respects model's max_seq_len, records truncated_len
- **Tenant Isolation**: All vectors tagged with org_id for multi-tenant filtering
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import UTC, datetime

import dramatiq

from heimdex_common.config import get_config
from heimdex_common.db import get_db
from heimdex_common.embeddings import get_adapter
from heimdex_common.models import JobStatus
from heimdex_common.repositories import JobRepository
from heimdex_common.vector import ensure_collection, point_id_for, upsert_point

logger = logging.getLogger(__name__)

# Note: Broker is configured in heimdex_worker.tasks module
# Both modules share the same broker instance set by dramatiq.set_broker()


def _update_job_status(
    job_id: str,
    status: JobStatus | None = None,
    stage: str | None = None,
    progress: int | None = None,
    result: dict | None = None,
    error: str | None = None,
) -> None:
    """
    Centralized helper for updating job status in the database.

    This function provides a consistent, transactional way for actors to report
    their progress. It encapsulates the interaction with the JobRepository.

    Args:
        job_id: The UUID of the job to update.
        status: The new JobStatus of the job.
        stage: The current processing stage to be recorded in a JobEvent.
        progress: The current progress percentage (0-100).
        result: The final result of the job, to be stored in a JobEvent.
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


def _compute_text_hash(text: str) -> str:
    """
    Compute SHA256 hash of text for idempotency and deduplication.

    Returns only the first 16 characters (64 bits) for compact storage.

    Args:
        text: Input text to hash

    Returns:
        First 16 characters of hex-encoded SHA256 hash
    """
    hash_obj = hashlib.sha256(text.encode("utf-8"))
    return hash_obj.hexdigest()[:16]


def _truncate_text(text: str, max_len: int | None) -> tuple[str, int]:
    """
    Truncate text to maximum length, respecting UTF-8 boundaries.

    Args:
        text: Input text to truncate
        max_len: Maximum character length (None = no truncation)

    Returns:
        Tuple of (truncated_text, truncated_length)
        If no truncation occurred, truncated_length equals original length
    """
    if max_len is None:
        return text, len(text)

    if len(text) <= max_len:
        return text, len(text)

    # Truncate safely (though Python strings handle this well)
    truncated = text[:max_len]
    return truncated, len(truncated)


@dramatiq.actor(
    actor_name="dispatch_embed_text",
    max_retries=3,
    min_backoff=1000,
    max_backoff=60000,
)
def dispatch_embed_text(
    job_id: str,
    *,
    org_id: str,
    asset_id: str,
    segment_id: str,
    text: str,
    model: str | None = None,
    model_ver: str | None = None,
) -> None:
    """
    Dramatiq actor that generates real embeddings and stores them in Qdrant.

    This actor replaces the mock_embedding flow with production-ready ML inference.
    It uses the embedding adapter pattern to support pluggable models, handles
    text truncation, and implements strict PII minimization (no raw text in Qdrant).

    Key Responsibilities:
    1. **Idempotency Check**: Verify job is not already complete (terminal-state guard)
    2. Load embedding adapter from factory (respects EMBEDDING_MODEL_NAME env var)
    3. Validate text is non-empty, compute text_len and text_hash
    4. Truncate text if exceeds model's max_seq_len, record truncated_len
    5. Generate real embedding vector via adapter.embed()
    6. Compute deterministic point_id (NO text_hash, per design decision)
    7. Upsert vector to Qdrant with PII-minimized payload
    8. Mark job as SUCCEEDED with metadata result

    PII Minimization Policy:
    - **Stored in Qdrant**: org_id, asset_id, segment_id, modality, model, model_ver,
      text_len, truncated_len, job_id
    - **Never stored in Qdrant**: raw text
    - text_hash is used for job deduplication but NOT stored in Qdrant payload

    Idempotency Semantics:
    - job_key (at API level) includes text_hash → prevents duplicate processing
    - point_id (here) excludes text_hash → allows vector updates (latest-wins)

    Args:
        job_id: The UUID of the job being processed
        org_id: Organization/tenant ID for multi-tenant isolation
        asset_id: Unique identifier of the asset being embedded
        segment_id: Identifier for a segment within the asset (e.g., chunk index)
        text: The raw text to embed (PII-sensitive, not stored in Qdrant)
        model: Optional model name override (defaults to EMBEDDING_MODEL_NAME env var)
        model_ver: Optional model version tag for tracking (e.g., "v1")

    Raises:
        ValueError: If text is empty or invalid
        Exception: On unexpected errors, triggering Dramatiq's retry mechanism
    """
    logger.info(
        f"dispatch_embed_text started: job_id={job_id}, org_id={org_id}, "
        f"asset_id={asset_id}, segment_id={segment_id}, model={model}"
    )

    # CRITICAL IDEMPOTENCY CHECK: Verify the job is not already in a terminal state
    with get_db() as session:
        repo = JobRepository(session)
        job = repo.get_job_by_id(uuid.UUID(job_id))

        if not job:
            logger.error(f"Job not found: {job_id}")
            return

        terminal_states = {
            JobStatus.SUCCEEDED,
            JobStatus.FAILED,
            JobStatus.CANCELED,
            JobStatus.DEAD_LETTER,
        }
        if job.status in terminal_states:
            logger.info(
                f"Idempotent no-op: job {job_id} already in terminal state {job.status.value}"
            )
            return

    try:
        _update_job_status(job_id, status=JobStatus.RUNNING, progress=0, stage="initializing")

        # Load embedding adapter (singleton, cached per process)
        logger.info("Loading embedding adapter")
        _update_job_status(job_id, stage="loading_adapter", progress=10)
        adapter = get_adapter()

        logger.info(
            f"Adapter loaded: model={adapter.name}, dim={adapter.dim}, "
            f"max_seq_len={adapter.max_seq_len}"
        )

        # Validate text is non-empty
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        # Compute metadata (for result/logging, NOT stored in Qdrant payload)
        text_len = len(text)
        text_hash = _compute_text_hash(text)

        # Truncate text if necessary
        _update_job_status(job_id, stage="preprocessing_text", progress=20)

        # Use adapter's max_seq_len if available, otherwise fallback to 2000 chars
        max_len = adapter.max_seq_len if adapter.max_seq_len else 2000
        text_to_embed, truncated_len = _truncate_text(text, max_len)

        if truncated_len < text_len:
            logger.warning(
                f"Text truncated: original_len={text_len}, truncated_len={truncated_len}, "
                f"max_len={max_len}, job_id={job_id}"
            )
        else:
            logger.info(f"Text length within limits: text_len={text_len}, job_id={job_id}")

        # Generate real embedding
        logger.info(f"Generating embedding: text_len={truncated_len}")
        _update_job_status(job_id, stage="generating_embedding", progress=40)

        vector = adapter.embed(text_to_embed)

        logger.info(f"Embedding generated: vector_dim={len(vector)}, job_id={job_id}")

        # Get configuration
        config = get_config()
        vector_size = config.vector_size
        collection_name = "embeddings"

        # Validate vector dimension matches configuration
        if len(vector) != vector_size:
            raise ValueError(
                f"Dimension mismatch: adapter produced {len(vector)}-dim vector "
                f"but VECTOR_SIZE={vector_size}. Check your configuration!"
            )

        # Ensure the Qdrant collection exists (idempotent)
        logger.info(f"Ensuring collection: {collection_name}")
        _update_job_status(job_id, stage="ensuring_collection", progress=60)
        ensure_collection(name=collection_name, vector_size=vector_size, distance="Cosine")

        # Generate deterministic point ID (NO text_hash, per design decision)
        # This enables overwrite semantics: same (org, asset, segment, model) = same point
        effective_model = model if model else adapter.name
        effective_model_ver = model_ver if model_ver else "v1"

        point_id = point_id_for(
            org_id=org_id,
            asset_id=asset_id,
            segment_id=segment_id,
            model=effective_model,
            model_ver=effective_model_ver,
        )

        logger.info(f"Upserting vector: point_id={point_id}, collection={collection_name}")
        _update_job_status(job_id, stage="upserting_vector", progress=80)

        # Upsert to Qdrant with PII-minimized payload
        # CRITICAL: Do NOT include raw text in payload!
        payload = {
            "org_id": org_id,
            "asset_id": asset_id,
            "segment_id": segment_id,
            "modality": "text",  # Future: support "image", "audio", etc.
            "model": effective_model,
            "model_ver": effective_model_ver,
            "text_len": text_len,
            "truncated_len": truncated_len,
            "job_id": job_id,
            # Note: text_hash is NOT stored (used only for job deduplication)
        }

        upsert_point(
            collection_name=collection_name,
            point_id=point_id,
            vector=vector,
            payload=payload,
        )

        # Mark job as completed successfully
        result = {
            "point_id": point_id,
            "collection": collection_name,
            "vector_size": len(vector),
            "model": effective_model,
            "model_ver": effective_model_ver,
            "text_len": text_len,
            "truncated_len": truncated_len,
            "text_hash": text_hash,  # Include in result for debugging (not in Qdrant)
            "org_id": org_id,
            "asset_id": asset_id,
            "segment_id": segment_id,
            "completed_at": datetime.now(UTC).isoformat(),
        }

        _update_job_status(
            job_id, status=JobStatus.SUCCEEDED, progress=100, result=result, stage="completed"
        )
        logger.info(f"dispatch_embed_text succeeded: job_id={job_id}, point_id={point_id}")

    except ValueError as e:
        # Validation errors (empty text, dimension mismatch) should not be retried
        logger.error(f"Validation error: {e}, job_id={job_id}")
        _update_job_status(job_id, status=JobStatus.FAILED, error=str(e), stage="validation_error")
        # Do NOT raise - this is a permanent failure, retries won't help
        return

    except Exception as e:
        # Unexpected errors: log, mark as failed, and re-raise for Dramatiq retry
        logger.exception(f"dispatch_embed_text failed: job_id={job_id}, error={e}")
        _update_job_status(job_id, status=JobStatus.FAILED, error=str(e), stage="error")
        raise
