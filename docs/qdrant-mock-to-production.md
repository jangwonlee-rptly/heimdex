# Migration Guide: Mock Embeddings → Production Embeddings

**Current State**: Mock embeddings using deterministic random vectors
**Target State**: Real embeddings using production ML models
**Difficulty**: Medium
**Estimated Time**: 2-3 weeks

---

## Overview

This guide covers the step-by-step process to migrate from the mock embedding implementation to a production-ready system with real ML models.

### What Changes

| Component | Mock (Current) | Production (Target) |
|-----------|----------------|---------------------|
| **Model** | numpy random seed | SentenceTransformers / OpenAI |
| **Vectors** | Random floats | Semantic embeddings |
| **Endpoint** | `/vectors/mock` | `/vectors/embed` |
| **Actor** | `mock_embedding` | `generate_embedding` |
| **Input** | asset_id + segment_id | text content |
| **GPU** | Not required | Recommended |
| **Latency** | <10ms | 50-500ms |

### What Stays the Same

- ✅ Qdrant infrastructure
- ✅ Repository layer (`qdrant_repo.py`)
- ✅ Point ID generation (deterministic UUIDs)
- ✅ Idempotency guarantees
- ✅ Tenant isolation
- ✅ Job tracking
- ✅ Transactional outbox
- ✅ Health probes

---

## Phase 1: Model Selection & Testing (Week 1)

### Step 1.1: Evaluate Models

Create a test script to compare models:

```python
# scripts/evaluate_models.py
from sentence_transformers import SentenceTransformer
import numpy as np

models = {
    "minilm-l6-v2": "sentence-transformers/all-MiniLM-L6-v2",
    "mpnet-base": "sentence-transformers/all-mpnet-base-v2",
    "bert-base": "sentence-transformers/bert-base-nli-mean-tokens",
}

test_texts = [
    "The quick brown fox jumps over the lazy dog.",
    "A fast auburn canine leaps above an idle hound.",  # Similar meaning
    "Database indexing improves query performance.",     # Different topic
]

for name, model_id in models.items():
    print(f"\nTesting {name}...")
    model = SentenceTransformer(model_id)

    # Generate embeddings
    embeddings = model.encode(test_texts)

    # Measure similarity
    from sklearn.metrics.pairwise import cosine_similarity
    sim_matrix = cosine_similarity(embeddings)

    print(f"Vector size: {embeddings[0].shape[0]}")
    print(f"Similarity (1-2): {sim_matrix[0][1]:.3f}")  # Should be high
    print(f"Similarity (1-3): {sim_matrix[0][2]:.3f}")  # Should be low
```

Run and compare:
```bash
python scripts/evaluate_models.py
```

**Decision Criteria**:
- Vector size (smaller = faster search)
- Similarity scores (higher for similar text = better)
- Inference speed (measure on your hardware)

### Step 1.2: Benchmark Performance

```python
# scripts/benchmark_model.py
import time
import torch
from sentence_transformers import SentenceTransformer

model_id = "sentence-transformers/all-MiniLM-L6-v2"
model = SentenceTransformer(model_id)

# Test with GPU
device = "cuda" if torch.cuda.is_available() else "cpu"
model = model.to(device)

test_text = "This is a test sentence." * 50  # ~500 chars

# Warmup
for _ in range(10):
    model.encode([test_text])

# Benchmark
times = []
for _ in range(100):
    start = time.perf_counter()
    embedding = model.encode([test_text])
    elapsed = (time.perf_counter() - start) * 1000
    times.append(elapsed)

print(f"Device: {device}")
print(f"p50: {np.percentile(times, 50):.2f}ms")
print(f"p95: {np.percentile(times, 95):.2f}ms")
print(f"p99: {np.percentile(times, 99):.2f}ms")
```

**Targets**:
- p95 < 100ms (with GPU)
- p95 < 500ms (with CPU)

### Step 1.3: Document Decision

Create `docs/model-selection-decision.md`:

```markdown
# Embedding Model Selection

**Date**: YYYY-MM-DD
**Decision**: sentence-transformers/all-MiniLM-L6-v2

## Rationale
- Vector size: 384 (good balance of quality and speed)
- Quality: 0.85 similarity for paraphrases, 0.15 for unrelated text
- Speed: 45ms p95 with GPU, 320ms p95 without
- License: Apache 2.0 (commercial use OK)
- Maturity: 50M+ downloads, well-tested

## Alternatives Considered
- all-mpnet-base-v2: Higher quality (768-dim) but slower
- OpenAI text-embedding-3-small: Excellent quality but costs $0.02/1M tokens

## Next Steps
1. Add model to worker container
2. Implement generate_embedding actor
3. Test with production-like data
```

---

## Phase 2: Worker Implementation (Week 1-2)

### Step 2.1: Add GPU Support to Worker

Update `apps/worker/Dockerfile`:

```dockerfile
FROM nvidia/cuda:12.1.0-base-ubuntu22.04

# Install Python 3.11
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3.11-dev \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# ... rest of Dockerfile ...

# Install PyTorch with CUDA support
RUN pip install torch --index-url https://download.pytorch.org/whl/cu121

# Install model dependencies
RUN pip install sentence-transformers
```

Update `deploy/docker-compose.yml`:

```yaml
worker:
  build:
    context: ..
    dockerfile: apps/worker/Dockerfile
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
```

### Step 2.2: Create Model Manager

Create `packages/common/src/heimdex_common/ml/model_manager.py`:

```python
"""Model loading and caching for embedding generation."""
from __future__ import annotations

from functools import lru_cache
from sentence_transformers import SentenceTransformer
import logging

logger = logging.getLogger(__name__)

# Model registry: name -> HuggingFace ID
MODELS = {
    "minilm-l6-v2": "sentence-transformers/all-MiniLM-L6-v2",
    "mpnet-base": "sentence-transformers/all-mpnet-base-v2",
}

@lru_cache(maxsize=5)
def load_model(model_name: str) -> SentenceTransformer:
    """
    Load and cache an embedding model.

    Models are cached in memory for fast reuse.
    """
    if model_name not in MODELS:
        raise ValueError(f"Unknown model: {model_name}. Available: {list(MODELS.keys())}")

    model_id = MODELS[model_name]
    logger.info(f"Loading model: {model_id}")

    model = SentenceTransformer(model_id)

    # Move to GPU if available
    import torch
    if torch.cuda.is_available():
        model = model.to("cuda")
        logger.info("Model loaded on GPU")
    else:
        logger.warning("GPU not available, using CPU")

    return model

def generate_embedding(text: str, model_name: str = "minilm-l6-v2") -> list[float]:
    """Generate embedding for text."""
    model = load_model(model_name)
    embedding = model.encode(text, convert_to_numpy=True)
    return embedding.tolist()
```

### Step 2.3: Create Production Actor

Add to `apps/worker/src/heimdex_worker/tasks.py`:

```python
@dramatiq.actor(
    actor_name="generate_embedding",
    max_retries=3,
    min_backoff=1000,
    max_backoff=60000,
)
def generate_embedding(
    job_id: str,
    org_id: str,
    asset_id: str,
    segment_id: str,
    text: str,
    model: str = "minilm-l6-v2"
) -> None:
    """
    Generate real embedding for text and store in Qdrant.

    Replaces mock_embedding with production model inference.
    """
    log_event("INFO", "embedding_started", job_id=job_id, model=model)

    # Idempotency check
    with get_db() as session:
        repo = JobRepository(session)
        job = repo.get_job_by_id(uuid.UUID(job_id))

        if not job:
            log_event("ERROR", "job_not_found", job_id=job_id)
            return

        if job.status in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELED, JobStatus.DEAD_LETTER}:
            log_event("INFO", "job_already_terminal", job_id=job_id, status=job.status.value)
            return

    try:
        _update_job_status(job_id, status=JobStatus.RUNNING, progress=0, stage="initializing")

        # Get config
        config = get_config()
        collection_name = "embeddings"

        # Ensure collection
        log_event("INFO", "ensuring_collection", job_id=job_id)
        _update_job_status(job_id, stage="ensuring_collection", progress=10)
        ensure_collection(name=collection_name, vector_size=config.vector_size, distance="Cosine")

        # Generate embedding
        log_event("INFO", "generating_embedding", job_id=job_id, model=model, text_length=len(text))
        _update_job_status(job_id, stage="generating_embedding", progress=30)

        from heimdex_common.ml.model_manager import generate_embedding as gen_emb
        vector = gen_emb(text, model_name=model)

        # Generate point ID
        point_id = point_id_for(
            org_id=org_id,
            asset_id=asset_id,
            segment_id=segment_id,
            model=model,
            model_ver="v1",
        )

        # Upsert to Qdrant
        log_event("INFO", "upserting_vector", job_id=job_id, point_id=point_id)
        _update_job_status(job_id, stage="upserting_vector", progress=70)

        payload = {
            "org_id": org_id,
            "asset_id": asset_id,
            "segment_id": segment_id,
            "model": model,
            "model_ver": "v1",
            "text_preview": text[:200],  # First 200 chars for debugging
        }

        upsert_point(
            collection_name=collection_name,
            point_id=point_id,
            vector=vector,
            payload=payload,
        )

        # Success
        result = {
            "point_id": point_id,
            "collection": collection_name,
            "vector_size": len(vector),
            "model": model,
            "org_id": org_id,
            "asset_id": asset_id,
            "segment_id": segment_id,
            "completed_at": datetime.now(UTC).isoformat(),
        }

        _update_job_status(
            job_id, status=JobStatus.SUCCEEDED, progress=100, result=result, stage="completed"
        )
        log_event("INFO", "embedding_succeeded", job_id=job_id, point_id=point_id)

    except Exception as e:
        log_event("ERROR", "embedding_failed", job_id=job_id, error=str(e))
        _update_job_status(job_id, status=JobStatus.FAILED, error=str(e), stage="error")
        raise
```

### Step 2.4: Test Worker Locally

```bash
# Run worker with GPU
docker compose up -d worker

# Check logs
docker compose logs worker -f

# Should see:
# "Loading model: sentence-transformers/all-MiniLM-L6-v2"
# "Model loaded on GPU" (or "using CPU" if no GPU)
```

---

## Phase 3: API Implementation (Week 2)

### Step 3.1: Create Production Endpoint

Update `apps/api/src/heimdex_api/vectors.py`:

```python
class EmbeddingRequest(BaseModel):
    """Request to generate real embedding."""
    asset_id: str = Field(..., min_length=1)
    segment_id: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1, max_length=10000)
    model: str = Field(default="minilm-l6-v2")

class EmbeddingResponse(BaseModel):
    """Response after creating embedding job."""
    job_id: str
    asset_id: str
    segment_id: str
    model: str

@router.post("/embed", response_model=EmbeddingResponse)
async def create_embedding(
    request: EmbeddingRequest,
    ctx: Annotated[RequestContext, Depends(verify_jwt)],
) -> EmbeddingResponse:
    """
    Generate real embedding for text.

    Replaces /vectors/mock with production model inference.
    """
    org_id = uuid.UUID(ctx.org_id)

    # Job key includes model for idempotency
    payload_for_key = {
        "asset_id": request.asset_id,
        "segment_id": request.segment_id,
        "model": request.model,
    }

    job_key = make_job_key(org_id, "generate_embedding", payload_for_key)

    with get_db() as session:
        repo = JobRepository(session)

        # Idempotency check
        existing_job = repo.get_job_by_job_key(job_key)
        if existing_job:
            return EmbeddingResponse(
                job_id=str(existing_job.id),
                asset_id=request.asset_id,
                segment_id=request.segment_id,
                model=request.model,
            )

        # Create job
        job = Job(
            id=uuid.uuid4(),
            org_id=org_id,
            type="generate_embedding",
            status=JobStatus.QUEUED,
            job_key=job_key,
            requested_by=ctx.user_id,
        )
        session.add(job)
        session.flush()

        # Log event
        repo.log_job_event(
            job_id=job.id,
            prev_status=None,
            next_status=JobStatus.QUEUED.value,
        )

        # Create outbox
        outbox_payload = {
            "queue_name": "default",
            "args": (
                str(job.id),
                ctx.org_id,
                request.asset_id,
                request.segment_id,
                request.text,
                request.model,
            ),
            "kwargs": {},
            "options": {},
        }

        outbox_message = Outbox(
            job_id=job.id,
            task_name="generate_embedding",
            payload=outbox_payload,
        )
        session.add(outbox_message)

        session.commit()
        job_id = str(job.id)

    return EmbeddingResponse(
        job_id=job_id,
        asset_id=request.asset_id,
        segment_id=request.segment_id,
        model=request.model,
    )
```

### Step 3.2: Add Search Endpoint

```python
class SearchRequest(BaseModel):
    """Semantic search request."""
    query: str = Field(..., min_length=1, max_length=1000)
    limit: int = Field(default=10, ge=1, le=100)
    asset_id: str | None = None  # Optional: filter to specific asset

class SearchResult(BaseModel):
    """Single search result."""
    point_id: str
    score: float
    asset_id: str
    segment_id: str
    text_preview: str

class SearchResponse(BaseModel):
    """Search results."""
    results: list[SearchResult]
    query: str
    limit: int

@router.post("/search", response_model=SearchResponse)
async def search_vectors(
    request: SearchRequest,
    ctx: Annotated[RequestContext, Depends(verify_jwt)],
) -> SearchResponse:
    """
    Semantic search across embeddings.

    Embeds query text and finds similar vectors in Qdrant.
    """
    from heimdex_common.ml.model_manager import generate_embedding
    from heimdex_common.vector import search
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    # Generate query embedding
    query_vector = generate_embedding(request.query, model_name="minilm-l6-v2")

    # Build filter for tenant isolation
    filter_conditions = [
        FieldCondition(key="org_id", match=MatchValue(value=ctx.org_id))
    ]

    # Optional: filter to specific asset
    if request.asset_id:
        filter_conditions.append(
            FieldCondition(key="asset_id", match=MatchValue(value=request.asset_id))
        )

    query_filter = Filter(must=filter_conditions)

    # Search Qdrant
    raw_results = search(
        collection_name="embeddings",
        vector=query_vector,
        limit=request.limit,
        query_filter=query_filter,
    )

    # Format results
    results = [
        SearchResult(
            point_id=r["id"],
            score=r["score"],
            asset_id=r["payload"]["asset_id"],
            segment_id=r["payload"]["segment_id"],
            text_preview=r["payload"].get("text_preview", ""),
        )
        for r in raw_results
    ]

    return SearchResponse(
        results=results,
        query=request.query,
        limit=request.limit,
    )
```

### Step 3.3: Test Endpoints

```bash
# Create embedding
curl -X POST http://localhost:8000/vectors/embed \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "asset_id": "doc-123",
    "segment_id": "chunk-0",
    "text": "The quick brown fox jumps over the lazy dog."
  }' | jq

# Wait for job to complete (~500ms)
sleep 1

# Search
curl -X POST http://localhost:8000/vectors/search \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "fast animal leaping",
    "limit": 5
  }' | jq
```

---

## Phase 4: Data Migration (Week 2-3)

### Step 4.1: Migrate Existing Mock Vectors (Optional)

If you have mock vectors in production that need real embeddings:

```python
# scripts/migrate_mock_to_real.py
"""Regenerate embeddings for all mock vectors."""
import requests
from heimdex_common.auth import create_dev_token

API_URL = "http://localhost:8000"

# Get all assets with mock embeddings
# (This assumes you have an endpoint to list assets)
assets = requests.get(f"{API_URL}/assets", headers=headers).json()

for asset in assets:
    # Fetch text content
    text = asset["text"]

    # Create real embedding job
    response = requests.post(
        f"{API_URL}/vectors/embed",
        headers=headers,
        json={
            "asset_id": asset["id"],
            "segment_id": "full_text",
            "text": text,
            "model": "minilm-l6-v2"
        }
    )

    print(f"Migrated {asset['id']}: {response.json()['job_id']}")
```

### Step 4.2: Clean Up Mock Vectors

Once real vectors are in place:

```bash
# Delete mock collection (optional)
curl -X DELETE http://localhost:6333/collections/embeddings_mock

# Or delete all mock points
# (Identify by payload.model == "mock")
```

---

## Phase 5: Deprecation & Cleanup (Week 3)

### Step 5.1: Deprecate Mock Endpoint

Add deprecation warning to `/vectors/mock`:

```python
@router.post("/mock", response_model=MockEmbeddingResponse, deprecated=True)
async def create_mock_embedding(...):
    """
    DEPRECATED: Use POST /vectors/embed instead.

    This endpoint generates mock embeddings for testing only.
    It will be removed in v2.0.0.
    """
    warnings.warn(
        "POST /vectors/mock is deprecated. Use POST /vectors/embed.",
        DeprecationWarning
    )
    # ... existing implementation ...
```

### Step 5.2: Remove Mock Code (v2.0.0)

After all clients have migrated:

1. Delete `mock_embedding` actor from `tasks.py`
2. Delete `POST /vectors/mock` from `vectors.py`
3. Update tests to use real embeddings
4. Remove numpy dependency (if not used elsewhere)

---

## Testing Strategy

### Unit Tests

```python
# tests/test_embedding_generation.py
def test_generate_embedding():
    """Test embedding generation."""
    from heimdex_common.ml.model_manager import generate_embedding

    text = "The quick brown fox"
    embedding = generate_embedding(text, model_name="minilm-l6-v2")

    assert len(embedding) == 384
    assert all(isinstance(x, float) for x in embedding)

def test_embedding_reproducibility():
    """Embeddings should be identical for same text."""
    from heimdex_common.ml.model_manager import generate_embedding

    text = "Test reproducibility"
    emb1 = generate_embedding(text)
    emb2 = generate_embedding(text)

    assert emb1 == emb2
```

### Integration Tests

```python
# tests/test_embedding_api.py
async def test_create_and_search_embedding(client, auth_token):
    """Test full flow: create embedding → search."""
    # Create embedding
    response = await client.post(
        "/vectors/embed",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={
            "asset_id": "test-doc",
            "segment_id": "chunk-0",
            "text": "The database stores structured data efficiently."
        }
    )
    assert response.status_code == 200
    job_id = response.json()["job_id"]

    # Wait for completion
    await wait_for_job(client, job_id, auth_token)

    # Search with similar query
    response = await client.post(
        "/vectors/search",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={
            "query": "efficient data storage system",
            "limit": 10
        }
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) > 0

    # First result should be our document (high similarity)
    assert results[0]["asset_id"] == "test-doc"
    assert results[0]["score"] > 0.7  # High cosine similarity
```

---

## Rollback Plan

If production deployment fails:

### Immediate Rollback

```bash
# Revert to previous API version
kubectl rollout undo deployment/api

# Disable new endpoints via feature flag
export ENABLE_REAL_EMBEDDINGS=false

# Continue using mock embeddings
# (Clients can still call /vectors/mock)
```

### Data Rollback

```bash
# Restore Qdrant snapshot
curl -X PUT http://qdrant:6333/collections/embeddings/snapshots/recover \
  -H "Content-Type: application/json" \
  -d '{"location": "file:///qdrant/snapshots/embeddings-backup.snapshot"}'
```

---

## Success Criteria

Migration is successful when:

- ✅ Workers generate real embeddings (<500ms p95 latency)
- ✅ Search returns semantically relevant results (>0.7 similarity for paraphrases)
- ✅ All tests pass (unit, integration, load)
- ✅ Production error rate <1%
- ✅ Documentation updated
- ✅ Team trained on new endpoints

---

## FAQ

**Q: Can I run mock and real embeddings simultaneously?**
A: Yes! Keep both endpoints during migration. Route new traffic to `/vectors/embed`, legacy to `/vectors/mock`.

**Q: Do I need GPU?**
A: Not required, but highly recommended. GPU is 10-50x faster for inference.

**Q: Can I use OpenAI embeddings instead of SentenceTransformers?**
A: Yes! Replace `generate_embedding()` with OpenAI API call. Consider cost (~$0.02 per 1M tokens).

**Q: How do I handle model updates?**
A: Include model version in `point_id_for()`. New model creates new points. Search across versions or filter to specific version.

**Q: What if embeddings change (model update, bug fix)?**
A: Regenerate all embeddings. Use batch processing to parallelize. Takes hours for 1M documents.

---

## Support

If you encounter issues during migration:

1. Check logs: `docker compose logs worker -f`
2. Review error traces in Qdrant
3. Test with small dataset first
4. Ask team for help in #heimdex-engineering

---

**Migration Owner**: [Assign owner]
**Start Date**: [YYYY-MM-DD]
**Target Completion**: [YYYY-MM-DD]
**Status**: 🔴 Not Started
