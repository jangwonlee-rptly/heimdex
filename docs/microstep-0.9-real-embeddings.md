# Microstep 0.9: Real Text Embeddings + Minimal Search

**Status**: ✅ Complete
**Date Completed**: 2025-10-31
**Type**: Feature Implementation + ML Integration

---

## Table of Contents

1. [Overview](#overview)
2. [What Was Implemented](#what-was-implemented)
3. [Architecture & Design Decisions](#architecture--design-decisions)
4. [API Endpoints](#api-endpoints)
5. [Testing & Validation](#testing--validation)
6. [Configuration Guide](#configuration-guide)
7. [Deployment Guide](#deployment-guide)
8. [Production Readiness Checklist](#production-readiness-checklist)
9. [Known TODOs & Limitations](#known-todos--limitations)
10. [Troubleshooting](#troubleshooting)
11. [What's Next](#whats-next)
12. [References](#references)

---

## Overview

### Purpose

This microstep replaces mock embeddings with **real ML-powered text embeddings** using SentenceTransformers, and adds **production-ready semantic search** capabilities. It builds on Microstep 0.8's Qdrant integration to provide:

- **Real embeddings** via SentenceTransformers models (replaces numpy-generated mock vectors)
- **Pluggable adapter pattern** for swapping embedding backends without code changes
- **Production API endpoints** for embedding generation (`/vectors/embed`) and semantic search (`/vectors/search`)
- **Query-time inference** for interactive search experiences
- **PII minimization** (raw text never stored in Qdrant, only metadata)
- **Fail-fast validation** to catch configuration errors at startup

### Scope

**What this IS:**

- Production-ready embedding generation with real ML models
- Semantic search with query-time inference
- Pluggable adapter pattern (easy to add OpenAI, Cohere, etc.)
- Comprehensive E2E tests
- Full documentation and configuration examples

**What this is NOT:**

- This does NOT include advanced reranking or hybrid search
- This does NOT include batch processing optimizations
- This does NOT include model fine-tuning or custom training

---

## What Was Implemented

### 1. Embedding Adapter Infrastructure

#### Protocol Definition

**File**: `packages/common/src/heimdex_common/embeddings/adapter.py`

```python
class EmbeddingAdapter(Protocol):
    """Protocol for embedding generation adapters."""

    @property
    def name(self) -> str:
        """Model name/identifier."""
        ...

    @property
    def dim(self) -> int:
        """Embedding vector dimensionality."""
        ...

    @property
    def max_seq_len(self) -> int | None:
        """Maximum sequence length in tokens."""
        ...

    def embed(self, text: str) -> list[float]:
        """Generate embedding vector for text."""
        ...
```

**Why Protocol?** Enables pluggable backends without inheritance—any class implementing these properties/methods is a valid adapter.

#### SentenceTransformer Adapter

**File**: `packages/common/src/heimdex_common/embeddings/adapters/sentence.py`

Key features:

- Device placement support (CPU/GPU via `EMBEDDING_DEVICE`)
- Automatic dimension detection
- Max sequence length inference from tokenizer
- Empty text validation
- Automatic truncation handling

#### Factory with Model Registry

**File**: `packages/common/src/heimdex_common/embeddings/factory.py`

**Model Registry** (short names for convenience):

```python
MODEL_REGISTRY = {
    "minilm-l6-v2": {
        "hf_id": "sentence-transformers/all-MiniLM-L6-v2",
        "dim": 384,
        "max_seq_len": 256,
        "description": "Fast, small model. Good for most use cases.",
    },
    "mpnet-base": {
        "hf_id": "sentence-transformers/all-mpnet-base-v2",
        "dim": 768,
        "max_seq_len": 384,
        "description": "Higher quality, slower. Best performance.",
    },
    "minilm-l12-v2": {
        "hf_id": "sentence-transformers/all-MiniLM-L12-v2",
        "dim": 384,
        "max_seq_len": 256,
        "description": "Balanced quality/speed.",
    },
}
```

**Singleton Factory**:

```python
@lru_cache(maxsize=1)
def get_adapter() -> EmbeddingAdapter:
    """Get configured adapter (cached singleton)."""
    # Reads EMBEDDING_BACKEND, EMBEDDING_MODEL_NAME, EMBEDDING_DEVICE
    # Returns cached adapter for process-global reuse
```

**Startup Validation**:

```python
def validate_adapter_dimension(vector_size: int) -> None:
    """Fail-fast if adapter dimension doesn't match VECTOR_SIZE."""
    # Prevents silent data corruption
    # Configurable via EMBEDDING_VALIDATE_ON_STARTUP
```

---

### 2. Worker Actor (dispatch_embed_text)

**File**: `apps/worker/src/heimdex_worker/embeddings.py`

#### Actor Signature

```python
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
```

#### Key Responsibilities

1. **Idempotency Check**: Terminal-state guard (same as mock_embedding)
2. **Load Adapter**: `adapter = get_adapter()` (singleton, cached)
3. **Validate & Truncate Text**:
   - Compute `text_len = len(text)`
   - Truncate if `text_len > adapter.max_seq_len`
   - Record `truncated_len` for metadata
4. **Generate Embedding**: `vector = adapter.embed(text_truncated)`
5. **Compute Point ID**: `point_id = point_id_for(org_id, asset_id, segment_id, model, model_ver)`
   - **CRITICAL**: Does NOT include `text_hash` (enables overwrite semantics)
6. **Upsert to Qdrant**: PII-minimized payload (no raw text)
7. **Mark Job SUCCEEDED**: Result includes `point_id`, `text_len`, `truncated_len`, `text_hash`

#### PII Minimization Policy

**Stored in Qdrant payload**:

- `org_id`, `asset_id`, `segment_id`, `modality`, `model`, `model_ver`
- `text_len`, `truncated_len`, `job_id`

**Never stored in Qdrant**:

- Raw text
- `text_hash` (used for job deduplication only, not stored in vector payload)

---

### 3. API Endpoints

**File**: `apps/api/src/heimdex_api/vectors.py`

#### POST /vectors/embed

**Purpose**: Creates a job to generate a real text embedding using ML models.

**Request Body**:

```json
{
  "asset_id": "doc_123",
  "segment_id": "chunk_0",
  "text": "The quick brown fox jumps over the lazy dog.",
  "model": "minilm-l6-v2",  // Optional, defaults to EMBEDDING_MODEL_NAME
  "model_ver": "v1"          // Optional
}
```

**Response**:

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "asset_id": "doc_123",
  "segment_id": "chunk_0"
}
```

**Idempotency Behavior**:

- `job_key` includes `text_hash` → same text for same segment returns existing job_id
- Creates job only if no matching job exists
- Uses transactional outbox pattern for exactly-once delivery

**Design Decision** (from user requirements):

- `job_key` includes `text_hash` (deduplicates identical text submissions)
- `point_id` excludes `text_hash` (allows vector updates via overwrite)

---

#### POST /vectors/search

**Purpose**: Performs semantic search using query-time inference.

**Request Body**:

```json
{
  "query_text": "machine learning algorithms",
  "limit": 5,           // Optional, default: 10, max: 100
  "asset_id": "doc_123", // Optional filter
  "segment_id": null     // Optional filter
}
```

**Response**:

```json
{
  "results": [
    {
      "point_id": "abc123...",
      "score": 0.95,
      "payload": {
        "org_id": "...",
        "asset_id": "doc_123",
        "segment_id": "chunk_0",
        "model": "sentence-transformers/all-MiniLM-L6-v2",
        "text_len": 42,
        "truncated_len": 42
      }
    }
  ],
  "query_model": "sentence-transformers/all-MiniLM-L6-v2",
  "query_model_ver": "v1",
  "total": 1
}
```

**Key Features**:

- **Query-time inference**: Embeds query on-the-fly (no job creation)
- **Tenant isolation**: Automatically filters by `org_id` from JWT
- **Server-side filters**: Optional filters by `asset_id`, `segment_id`
- **Fast response**: No worker queue, immediate results

---

### 4. Configuration & Environment

#### New Dependencies

**File**: `packages/common/pyproject.toml`

```toml
dependencies = [
    # ... existing deps ...
    "torch>=2.0.0,<3.0.0",
    "sentence-transformers>=2.2.0,<3.0.0",
]
```

#### New Environment Variables

**File**: `deploy/.env.example`

```bash
# Embedding Model Configuration
EMBEDDING_BACKEND=sentence             # Backend adapter (options: "sentence")
EMBEDDING_MODEL_NAME=minilm-l6-v2      # Short name or full HF ID
EMBEDDING_DEVICE=cpu                   # Device for inference (cpu, cuda, cuda:0)
EMBEDDING_VALIDATE_ON_STARTUP=true    # Fail-fast dimension validation
```

#### Model Pre-download (Docker)

**File**: `apps/worker/Dockerfile`

```dockerfile
# Pre-download default embedding model for deterministic builds
ENV SENTENCE_TRANSFORMERS_HOME=/app/.cache/sentence-transformers
RUN mkdir -p $SENTENCE_TRANSFORMERS_HOME && \
    python3 -c "from sentence_transformers import SentenceTransformer; \
    print('Pre-downloading default embedding model...'); \
    model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2', device='cpu'); \
    print(f'Model loaded: dim={model.get_sentence_embedding_dimension()}');" && \
    chown -R appuser:appuser $SENTENCE_TRANSFORMERS_HOME
```

**Why pre-download?**

- Deterministic builds (model baked into image)
- Faster startup (no download on first request)
- Fail-fast validation works correctly (model available at startup)

---

### 5. Startup Validation

**File**: `apps/worker/src/heimdex_worker/__init__.py`

```python
def _validate_startup_configuration() -> None:
    """
    Validate critical configuration at worker startup.

    Ensures adapter dimension matches VECTOR_SIZE before processing any jobs.
    """
    from heimdex_common.config import get_config
    from heimdex_common.embeddings.factory import validate_adapter_dimension

    config = get_config()
    validate_adapter_dimension(config.vector_size)

# Run validation when module is imported
_validate_startup_configuration()
```

**Why this matters:**

- Catches dimension mismatches immediately (fail-fast)
- Prevents silent data corruption
- Clear error message shows how to fix: "Set VECTOR_SIZE={adapter.dim} in .env"

**Example error message**:

```
❌ Embedding dimension mismatch!

   Model 'sentence-transformers/all-MiniLM-L6-v2' produces 384-dim vectors
   but VECTOR_SIZE=768

   → Fix: Set VECTOR_SIZE=384 in your .env file

   To bypass this check (not recommended):
   Set EMBEDDING_VALIDATE_ON_STARTUP=false
```

---

## Architecture & Design Decisions

### 1. Idempotency Semantics

#### Decision: Text Hash in job_key, NOT in point_id

**Problem**: How to handle:

- Duplicate submissions of identical text (waste)
- Updates to text for same segment (should overwrite)

**Solution** (user-approved):

- **job_key includes text_hash**: Same text for same segment → deduplicate job creation
- **point_id excludes text_hash**: Same segment, different text → overwrite vector (latest-wins)

**Example**:

```python
# Scenario 1: Submit same text twice
request_1 = {"asset": "A", "segment": "S", "text": "foo"}
request_2 = {"asset": "A", "segment": "S", "text": "foo"}
# Result: Same job_key → returns existing job_id (no duplicate work)

# Scenario 2: Update text for same segment
request_1 = {"asset": "A", "segment": "S", "text": "foo"}
request_2 = {"asset": "A", "segment": "S", "text": "bar"}
# Result: Different job_keys → creates new job
#         Same point_id → overwrites vector in Qdrant
```

---

### 2. PII Minimization

**Principle**: Raw text is PII-sensitive and should never be persisted in Qdrant.

**What we store**:

- In **Job table**: Nothing (job uses job_key hash, no text)
- In **Outbox table**: Raw text (temporary, deleted after dispatch)
- In **Qdrant payload**: Only metadata (lengths, hashes, IDs)
- In **Job result**: `text_hash` for debugging (not in Qdrant)

**Logging policy**:

- Never log `text` or raw outbox payloads
- Only log lengths, hashes, IDs

---

### 3. Truncation Handling

**Problem**: Models have max sequence length limits (e.g., 256 tokens for MiniLM-L6).

**Solution**:

1. Detect `max_seq_len` from adapter
2. If `text_len > max_seq_len`: truncate text
3. Record both `text_len` (original) and `truncated_len` (after truncation)
4. Log warning if truncation occurred

**Example**:

```python
text_len = 500           # Original text length
max_seq_len = 256        # Model's max
truncated_len = 256      # After truncation

logger.warning(
    f"Text truncated: original_len={text_len}, "
    f"truncated_len={truncated_len}, max_len={max_seq_len}"
)
```

---

### 4. Pluggable Adapter Pattern

**Why Protocol instead of ABC?**

- Protocols are structural (duck typing)
- No inheritance required
- Easier to add external adapters

**How to add a new adapter**:

1. Create class implementing `EmbeddingAdapter` protocol
2. Add to factory's backend selection logic
3. Update `MODEL_REGISTRY` if using short names

**Example: Adding OpenAI adapter** (future):

```python
class OpenAIAdapter:
    def __init__(self, model_id: str, api_key: str):
        self._client = OpenAI(api_key=api_key)
        self._model_id = model_id

    @property
    def name(self) -> str:
        return self._model_id

    @property
    def dim(self) -> int:
        return 1536 if "ada-002" in self._model_id else 3072

    @property
    def max_seq_len(self) -> int | None:
        return 8191

    def embed(self, text: str) -> list[float]:
        response = self._client.embeddings.create(
            input=text, model=self._model_id
        )
        return response.data[0].embedding

# In factory.py:
if backend == "openai":
    return OpenAIAdapter(model_name, api_key=os.getenv("OPENAI_API_KEY"))
```

---

## API Endpoints

### Summary Table

| Endpoint | Method | Purpose | Creates Job? | Requires Worker? |
|----------|--------|---------|-------------|------------------|
| `/vectors/mock` | POST | Mock embedding (testing) | Yes | Yes |
| `/vectors/embed` | POST | Real embedding generation | Yes | Yes |
| `/vectors/search` | POST | Semantic search | No | No |

### Authentication

All endpoints require JWT authentication:

```bash
curl -X POST http://localhost:8000/vectors/embed \
  -H "Authorization: Bearer <jwt_token>" \
  -H "Content-Type: application/json" \
  -d '{"asset_id": "doc_123", "segment_id": "chunk_0", "text": "..."}'
```

**Dev mode** (for local testing):

```bash
# In .env:
AUTH_PROVIDER=dev
DEV_JWT_SECRET=local-dev-secret

# Generate dev token:
python3 -c "
import jwt
token = jwt.encode(
    {'sub': 'test-user', 'org_id': 'test-org', 'iss': 'heimdex-test'},
    'local-dev-secret',
    algorithm='HS256'
)
print(token)
"
```

---

## Testing & Validation

### E2E Test Suite

**File**: `packages/common/tests/test_embeddings_e2e.py`

#### Test: test_embed_text_e2e

**Flow**:

1. POST `/vectors/embed` with test text
2. Poll GET `/jobs/{job_id}` until SUCCEEDED
3. Verify result contains `point_id`, metadata
4. POST `/vectors/search` with same text
5. Verify top result matches `point_id` (score > 0.99)

#### Test: test_semantic_search_similarity

**Flow**:

1. Embed "A large furry dog is running in the park"
2. Search "A big hairy canine is jogging outdoors"
3. Verify search finds original text (0.5 < score < 0.99)

#### Test: test_idempotent_embed_request

**Flow**:

1. POST same request twice
2. Verify returns same `job_id` (no duplicate work)

#### Test: test_vector_overwrite_semantics

**Flow**:

1. Embed text v1 for segment S
2. Embed text v2 for same segment S
3. Verify same `point_id` (overwrite)
4. Search for v2, verify high score (latest wins)

### Running Tests

```bash
# Set E2E environment
export HEIMDEX_E2E_API_URL=http://localhost:8000
export DEV_JWT_SECRET=local-dev-secret

# Run all E2E tests
pytest packages/common/tests/test_embeddings_e2e.py -v

# Run specific test
pytest -k test_embed_text_e2e -v
```

**Prerequisites**:

- Full Heimdex stack running (`docker compose up`)
- Qdrant enabled (`ENABLE_QDRANT=true`)
- Worker running with embedding models loaded

---

## Configuration Guide

### Quick Start (Default Config)

**Minimal .env**:

```bash
# Vector Database
QDRANT_URL=http://qdrant:6333
VECTOR_SIZE=384

# Embedding Model (defaults are fine for most use cases)
EMBEDDING_BACKEND=sentence
EMBEDDING_MODEL_NAME=minilm-l6-v2
EMBEDDING_DEVICE=cpu
EMBEDDING_VALIDATE_ON_STARTUP=true
```

### Configuration Options

#### Choosing a Model

**Fast & Small** (default):

```bash
EMBEDDING_MODEL_NAME=minilm-l6-v2
VECTOR_SIZE=384
```

- Best for: Most use cases, development, testing
- Speed: Fast (~100ms per embedding on CPU)
- Quality: Good

**High Quality**:

```bash
EMBEDDING_MODEL_NAME=mpnet-base
VECTOR_SIZE=768
```

- Best for: Production, high-accuracy requirements
- Speed: Slower (~300ms per embedding on CPU)
- Quality: Best

**Balanced**:

```bash
EMBEDDING_MODEL_NAME=minilm-l12-v2
VECTOR_SIZE=384
```

- Best for: When you need better quality than L6 but not full mpnet cost
- Speed: Medium (~150ms per embedding on CPU)
- Quality: Better than L6

#### Using Custom HuggingFace Models

```bash
# Use full HuggingFace ID instead of short name
EMBEDDING_MODEL_NAME=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2

# IMPORTANT: Set VECTOR_SIZE to match model's dimension
# Check model card on HuggingFace for dimension
VECTOR_SIZE=384
```

#### GPU Acceleration

```bash
EMBEDDING_DEVICE=cuda      # Use first GPU
# or
EMBEDDING_DEVICE=cuda:0    # Specific GPU
# or
EMBEDDING_DEVICE=cpu       # Force CPU (default)
```

**Docker GPU support** (requires nvidia-docker):

```yaml
# docker-compose.yml
worker:
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
```

---

## Deployment Guide

### Development Environment

```bash
# 1. Update .env
cp deploy/.env.example deploy/.env
# Edit: Set VECTOR_SIZE=384, EMBEDDING_MODEL_NAME=minilm-l6-v2

# 2. Build images (includes model download)
docker compose build worker

# 3. Start stack
docker compose up -d

# 4. Verify worker startup
docker compose logs worker | grep "validation passed"
# Should see: ✓ Startup validation passed: embedding configuration is valid

# 5. Test embedding
curl -X POST http://localhost:8000/vectors/embed \
  -H "Authorization: Bearer $(python3 -c 'import jwt; print(jwt.encode({"sub": "u", "org_id": "o"}, "local-dev-secret", algorithm="HS256"))')" \
  -H "Content-Type: application/json" \
  -d '{"asset_id": "test", "segment_id": "s0", "text": "Hello world"}'
```

### Production Considerations

#### 1. Model Caching

**Current**: Model baked into Docker image

- ✅ Deterministic builds
- ✅ Fast startup
- ❌ Larger image size (~500MB with torch + model)

**Alternative** (not implemented): Volume-mounted cache

- ✅ Smaller images
- ❌ Slower first startup
- ❌ Requires shared volume

#### 2. Resource Limits

**Memory** (for minilm-l6-v2 on CPU):

```yaml
worker:
  deploy:
    resources:
      limits:
        memory: 2G    # Sufficient for default model
      reservations:
        memory: 1G
```

**CPU**:

```yaml
worker:
  deploy:
    resources:
      limits:
        cpus: '2.0'
      reservations:
        cpus: '1.0'
```

#### 3. Horizontal Scaling

Workers are stateless and can be scaled horizontally:

```bash
docker compose up -d --scale worker=3
```

**Load distribution**: Dramatiq + Redis automatically distribute jobs across workers.

---

## Production Readiness Checklist

### Critical Changes for Production

#### 1. Enable Qdrant in Readiness Probes

**Current (Development)**:

```bash
# deploy/.env
ENABLE_QDRANT=false  # Qdrant not required for healthz/readyz
```

**For Production**:

```bash
# deploy/.env
ENABLE_QDRANT=true   # ✅ Ensure Qdrant is healthy before accepting traffic
```

**Why**: In production, you want the API to report "not ready" if Qdrant is down, so load balancers don't route traffic to unhealthy instances.

---

#### 2. Switch to Production Auth

**Current (Development)**:

```bash
# deploy/.env
AUTH_PROVIDER=dev
DEV_JWT_SECRET=local-dev-secret  # ⚠️ Insecure for production!
```

**For Production**:

```bash
# deploy/.env
AUTH_PROVIDER=supabase
SUPABASE_JWKS_URL=https://<your-project>.supabase.co/auth/v1/jwks
AUTH_AUDIENCE=heimdex
AUTH_ISSUER=https://<your-project>.supabase.co/
```

**Why**: Dev mode uses simple HS256 tokens with a static secret. Production requires proper JWKS-based verification with RS256 (Supabase or your auth provider).

---

#### 3. Choose Production Model & Validate Config

**Current (Development)**:

```bash
# deploy/.env
EMBEDDING_MODEL_NAME=minilm-l6-v2  # Fast, but lower quality
VECTOR_SIZE=384
EMBEDDING_DEVICE=cpu
```

**For Production** (recommended):

```bash
# deploy/.env
EMBEDDING_MODEL_NAME=mpnet-base    # ✅ Better quality for production
VECTOR_SIZE=768                    # ✅ Match model dimension!
EMBEDDING_DEVICE=cuda              # ✅ Use GPU if available
EMBEDDING_VALIDATE_ON_STARTUP=true # ✅ Always enabled for production
```

**Action Items**:

- [ ] Decide on production model based on quality/speed tradeoffs
- [ ] Update `VECTOR_SIZE` to match model dimension
- [ ] Rebuild worker image with new model: `docker compose build worker --no-cache`
- [ ] Test with real production data to validate quality

---

#### 4. Configure Resource Limits

**Current (Development)**: No resource limits

**For Production** (add to `docker-compose.yml` or Kubernetes manifests):

```yaml
services:
  worker:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 3G    # Increase for larger models (mpnet-base needs ~2.5G)
        reservations:
          cpus: '1.0'
          memory: 1.5G
      replicas: 3       # Scale horizontally for throughput
    restart_policy:
      condition: on-failure
      delay: 5s
      max_attempts: 3

  api:
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 1G
        reservations:
          cpus: '0.5'
          memory: 512M
      replicas: 2
```

**Action Items**:

- [ ] Benchmark memory usage with production model
- [ ] Set appropriate resource limits
- [ ] Configure horizontal scaling based on load

---

#### 5. Secure Secrets Management

**Current (Development)**:

```bash
# deploy/.env (plaintext file)
DEV_JWT_SECRET=local-dev-secret
```

**For Production**:

- [ ] Use secret management service (AWS Secrets Manager, GCP Secret Manager, HashiCorp Vault)
- [ ] Inject secrets via environment variables at runtime
- [ ] Never commit secrets to git
- [ ] Rotate secrets regularly

**Example (Kubernetes)**:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: heimdex-secrets
type: Opaque
data:
  supabase-jwks-url: <base64-encoded-url>
---
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      containers:
      - name: api
        env:
        - name: SUPABASE_JWKS_URL
          valueFrom:
            secretKeyRef:
              name: heimdex-secrets
              key: supabase-jwks-url
```

---

#### 6. Enable Monitoring & Observability

**Current (Development)**: Basic structured logging only

**For Production**:

**Add metrics collection** (not implemented yet, see TODOs):

```python
# Future: Add Prometheus metrics
from prometheus_client import Counter, Histogram

embedding_requests = Counter('heimdex_embedding_requests_total', 'Total embedding requests')
embedding_duration = Histogram('heimdex_embedding_duration_seconds', 'Embedding generation latency')
search_duration = Histogram('heimdex_search_duration_seconds', 'Search latency')
```

**Add distributed tracing** (not implemented yet, see TODOs):

```python
# Future: Add OpenTelemetry tracing
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

@tracer.start_as_current_span("embed_text")
def embed_text(...):
    ...
```

**Action Items**:

- [ ] Choose observability stack (Prometheus + Grafana, Datadog, New Relic)
- [ ] Add metrics instrumentation (see TODOs below)
- [ ] Set up dashboards for key metrics
- [ ] Configure alerting for critical issues

---

#### 7. Backup & Disaster Recovery

**Qdrant Data**:

```bash
# Create backup
docker exec heimdex-qdrant-1 qdrant-client snapshot create embeddings

# Export to volume
docker cp heimdex-qdrant-1:/qdrant/snapshots ./backups/

# Restore from snapshot
docker cp ./backups/embeddings-snapshot.tar.gz heimdex-qdrant-1:/qdrant/snapshots/
docker exec heimdex-qdrant-1 qdrant-client snapshot restore embeddings embeddings-snapshot.tar.gz
```

**PostgreSQL Data** (already implemented in Microstep 0.x):

```bash
# Backup
docker exec heimdex-pg-1 pg_dump -U heimdex heimdex > backup.sql

# Restore
docker exec -i heimdex-pg-1 psql -U heimdex heimdex < backup.sql
```

**Action Items**:

- [ ] Set up automated Qdrant snapshots (daily recommended)
- [ ] Configure off-site backup storage (S3, GCS)
- [ ] Test restore procedure regularly
- [ ] Document disaster recovery playbook

---

#### 8. Performance Testing & Benchmarking

**Before Production**:

```bash
# Benchmark embedding throughput
# Generate 1000 embeddings and measure time
time for i in {1..1000}; do
  curl -X POST http://localhost:8000/vectors/embed \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"asset_id\": \"bench\", \"segment_id\": \"$i\", \"text\": \"Test text $i\"}" &
done
wait

# Benchmark search latency
# Run 1000 searches and measure p50/p95/p99
for i in {1..1000}; do
  curl -w "%{time_total}\n" -o /dev/null -s \
    -X POST http://localhost:8000/vectors/search \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"query_text": "test query", "limit": 10}' >> latency.txt
done

# Analyze results
cat latency.txt | sort -n | awk 'BEGIN {c=0; sum=0} {a[c++]=$1; sum+=$1} END {print "p50:", a[int(c*0.5)], "p95:", a[int(c*0.95)], "p99:", a[int(c*0.99)], "avg:", sum/c}'
```

**Action Items**:

- [ ] Establish baseline performance metrics
- [ ] Load test with production-like traffic patterns
- [ ] Identify bottlenecks (CPU, memory, I/O)
- [ ] Tune worker concurrency, resource limits

---

### Production Deployment Checklist

Use this checklist before deploying to production:

- [ ] **Authentication**: Switch from `AUTH_PROVIDER=dev` to `AUTH_PROVIDER=supabase`
- [ ] **Secrets**: Move secrets to secure storage (not plaintext .env files)
- [ ] **Qdrant Readiness**: Set `ENABLE_QDRANT=true` in production
- [ ] **Model Selection**: Choose production model (`mpnet-base` recommended)
- [ ] **VECTOR_SIZE**: Verify matches model dimension
- [ ] **GPU Support**: Configure if available (`EMBEDDING_DEVICE=cuda`)
- [ ] **Resource Limits**: Set CPU/memory limits in docker-compose.yml or K8s
- [ ] **Horizontal Scaling**: Configure worker replicas based on load
- [ ] **Monitoring**: Set up metrics, logging, alerting
- [ ] **Backups**: Automated Qdrant snapshots + offsite storage
- [ ] **Load Testing**: Benchmark with production-like traffic
- [ ] **E2E Tests**: Run full test suite (`pytest packages/common/tests/test_embeddings_e2e.py`)
- [ ] **Documentation**: Update runbooks, disaster recovery procedures
- [ ] **Rollback Plan**: Test rollback procedure, have previous image tagged

---

## Known TODOs & Limitations

### TODOs Created in This Microstep

#### 1. Configurable model_ver in Search Response

**File**: `apps/api/src/heimdex_api/vectors.py:570`

**Current**:

```python
return SearchVectorsResponse(
    results=results,
    query_model=adapter.name,
    query_model_ver="v1",  # TODO: Make this configurable
    total=len(results),
)
```

**Issue**: `model_ver` is hardcoded to "v1"

**Fix**:

- Add `EMBEDDING_MODEL_VER` environment variable
- Read from config in factory
- Expose via adapter (or config)
- Use in search response

**Priority**: Low (cosmetic issue, doesn't affect functionality)

---

#### 2. Metrics & Observability Instrumentation

**Not implemented yet**:

- [ ] **Prometheus metrics** for embedding/search operations:

  ```python
  # Suggested metrics:
  - heimdex_embedding_requests_total (counter)
  - heimdex_embedding_duration_seconds (histogram)
  - heimdex_embedding_errors_total (counter)
  - heimdex_search_requests_total (counter)
  - heimdex_search_duration_seconds (histogram)
  - heimdex_search_results_count (histogram)
  - heimdex_model_cache_hits_total (counter)
  ```

- [ ] **Distributed tracing** with OpenTelemetry:
  - Trace embedding job lifecycle (API → Outbox → Worker → Qdrant)
  - Trace search requests (API → Adapter → Qdrant)
  - Include model inference time, Qdrant query time

- [ ] **Structured logging enhancements**:
  - Add `text_len`, `truncated_len`, `model` to all log messages
  - Add correlation IDs across API/worker boundaries

**Priority**: Medium-High (critical for production debugging)

**Files to modify**:

- `apps/api/src/heimdex_api/vectors.py` (add metrics decorators)
- `apps/worker/src/heimdex_worker/embeddings.py` (add metrics, tracing)
- `packages/common/src/heimdex_common/embeddings/adapters/sentence.py` (instrument inference)

---

#### 3. Batch Embedding Endpoint

**Not implemented yet**:

- [ ] Add `POST /vectors/embed/batch` endpoint
  - Accept array of texts in single request
  - Create single job that processes all texts
  - Optimize: batch inference via adapter (leverage GPU parallelism)
  - Return single job_id for entire batch

**Use Case**: Bulk document ingestion, re-indexing

**Example API**:

```json
POST /vectors/embed/batch
{
  "asset_id": "doc_123",
  "segments": [
    {"segment_id": "chunk_0", "text": "..."},
    {"segment_id": "chunk_1", "text": "..."},
    {"segment_id": "chunk_2", "text": "..."}
  ]
}
```

**Priority**: Medium (improves bulk ingestion performance)

**Files to create/modify**:

- `apps/api/src/heimdex_api/vectors.py` (new endpoint)
- `apps/worker/src/heimdex_worker/embeddings.py` (new actor: `dispatch_embed_batch`)

---

#### 4. Advanced Search Filters

**Current**: Simple filters (asset_id, segment_id)

**Not implemented yet**:

- [ ] Date range filters (e.g., embedded_after, embedded_before)
- [ ] Metadata filters (e.g., tags, categories, authors)
- [ ] Composite filters with OR logic (currently only AND)
- [ ] Geospatial filters (if location metadata added)

**Example API** (future):

```json
POST /vectors/search
{
  "query_text": "machine learning",
  "limit": 10,
  "filters": {
    "asset_id": {"$in": ["doc_123", "doc_456"]},
    "created_at": {"$gte": "2024-01-01", "$lt": "2024-12-31"},
    "tags": {"$contains": "tutorial"}
  }
}
```

**Priority**: Medium (depends on use case requirements)

**Files to modify**:

- `apps/api/src/heimdex_api/vectors.py` (extend SearchVectorsRequest)
- Build complex Qdrant Filter from request

---

#### 5. Reranking Support

**Not implemented yet**:

- [ ] Add cross-encoder reranking for top-K results
- [ ] Improves precision by re-scoring with more expensive model
- [ ] Typical flow: retrieve 100 candidates with bi-encoder (fast), rerank top 10 with cross-encoder (slow but accurate)

**Example Implementation**:

```python
from sentence_transformers import CrossEncoder

# In search endpoint (after initial search):
top_k = 100
rerank_k = 10

# 1. Get top_k candidates from Qdrant
candidates = client.search(query_vector, limit=top_k)

# 2. Rerank with cross-encoder
reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-12-v2')
pairs = [(request.query_text, candidate.payload['text']) for candidate in candidates]
scores = reranker.predict(pairs)

# 3. Sort by reranker scores, return top rerank_k
reranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)[:rerank_k]
```

**Priority**: Medium-High (significant quality improvement for production)

**Files to modify**:

- `apps/api/src/heimdex_api/vectors.py` (add reranking logic)
- Add reranker model to Docker image (or load dynamically)

---

#### 6. Model Version Tracking

**Current**: `model_ver` is optional, defaults to "v1"

**Issue**: No enforcement of version consistency, hard to track which vectors use which model version

**Not implemented yet**:

- [ ] Enforce `model_ver` parameter (make required?)
- [ ] Add model registry versioning (track model weights hash/version)
- [ ] Validate search query uses same model as indexed vectors
- [ ] Add migration path for model upgrades (re-embed all vectors with new model)

**Priority**: Low-Medium (becomes important when upgrading models)

---

#### 7. Multilingual Support

**Current**: Default model (minilm-l6-v2) is English-only

**For multilingual use cases**:

- [ ] Add multilingual models to registry:

  ```python
  "paraphrase-multilingual": {
      "hf_id": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
      "dim": 384,
      "languages": ["en", "de", "fr", "es", "it", "pt", "nl", ...],
  }
  ```

- [ ] Allow per-request model selection (instead of global `EMBEDDING_MODEL_NAME`)
- [ ] Handle language detection and automatic model routing

**Priority**: Low (depends on product requirements)

---

#### 8. Vector Deletion / Cleanup

**Current**: No endpoint to delete vectors

**Not implemented yet**:

- [ ] Add `DELETE /vectors/{point_id}` endpoint
- [ ] Add `DELETE /vectors/asset/{asset_id}` (bulk delete all segments for asset)
- [ ] Add worker actor for async deletion (if large scale)
- [ ] Add soft-delete option (mark as deleted, clean up later)

**Priority**: Medium (needed for data lifecycle management, GDPR compliance)

---

#### 9. Embedding Cache / Duplicate Detection

**Current**: Each request generates fresh embeddings (no cache)

**Optimization** (not implemented):

- [ ] Cache embeddings by `text_hash` (deduplicate across assets)
- [ ] Store in Redis or dedicated cache (avoid re-computing identical text)
- [ ] Add cache hit/miss metrics

**Trade-offs**:

- ✅ Reduces compute cost
- ❌ Adds cache management complexity
- ❌ Increases storage (cache + vectors)

**Priority**: Low (premature optimization, wait for production metrics)

---

#### 10. Async Search (Future Enhancement)

**Current**: `/vectors/search` is synchronous (query-time inference)

**For very large collections or slow models**:

- [ ] Add `/vectors/search/async` endpoint (creates job, returns job_id)
- [ ] Client polls job status like embedding jobs
- [ ] Useful for expensive searches (reranking, large top-k, complex filters)

**Priority**: Low (current sync approach is fine for most cases)

---

### Limitations & Caveats

#### 1. Text Truncation

**Limitation**: Models have max sequence length (256-384 tokens for default models)

**Current Behavior**: Truncate silently with warning log

**Caveat**: Truncation may lose important context (end of documents)

**Mitigations**:

- Use longer-context models (e.g., Longformer, BigBird) - not implemented
- Implement chunking strategies (overlap, semantic boundaries) - not implemented
- Record `truncated_len` in metadata (already implemented)

---

#### 2. Single Model per Worker Process

**Limitation**: Factory uses `@lru_cache(maxsize=1)` → one model per worker

**Current Behavior**: Cannot switch models per request

**Caveat**: All embeddings in single worker use same model

**Workarounds**:

- Run multiple worker pools with different `EMBEDDING_MODEL_NAME` (not implemented)
- Remove `@lru_cache` and reload model per request (very slow, not recommended)
- Implement model registry with lazy loading (not implemented)

---

#### 3. No Hybrid Search

**Limitation**: Pure semantic search only (no keyword/BM25 fusion)

**Current Behavior**: May miss exact keyword matches that semantic search doesn't capture

**Future Enhancement**: Hybrid search combining semantic + BM25

**Workaround**: Use search filters to narrow results, then semantic search

---

#### 4. No Automatic Re-embedding

**Limitation**: If you change models, old vectors are not automatically re-embedded

**Current Behavior**: Old vectors use old model, new vectors use new model

**Caveat**: Mixing models in same collection can degrade search quality

**Mitigation** (not implemented):

- Migration job to re-embed all vectors with new model
- Version-aware search (filter by `model` in query)
- Blue-green deployment (new collection, switch over)

---

#### 5. PII in Logs (Partial Risk)

**Limitation**: Worker logs may inadvertently contain text snippets in error messages

**Current Mitigation**: Never log `text` variable directly

**Remaining Risk**: Exception tracebacks may include text if validation fails

**Future Enhancement**: Add log scrubbing for PII patterns

---

## Troubleshooting

### Common Issues

#### 1. Dimension Mismatch Error

**Symptom**:

```
❌ Embedding dimension mismatch!
   Model 'sentence-transformers/all-MiniLM-L6-v2' produces 384-dim vectors
   but VECTOR_SIZE=768
```

**Solution**:

```bash
# Check model dimension in registry or HuggingFace
# Update VECTOR_SIZE in .env
VECTOR_SIZE=384

# Restart services
docker compose restart worker api
```

#### 2. Model Download Timeout

**Symptom**:

```
ERROR: Failed to download model from HuggingFace
```

**Solution**:

- Check internet connectivity
- Try pre-downloading model locally:

  ```bash
  python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"
  ```

- If behind proxy, set `HTTP_PROXY` env var

#### 3. Worker Fails to Start

**Symptom**:

```
ImportError: No module named 'sentence_transformers'
```

**Solution**:

```bash
# Rebuild worker image
docker compose build worker --no-cache

# Verify dependencies installed
docker compose run --rm worker pip list | grep sentence
```

#### 4. Search Returns No Results

**Possible causes**:

1. **Tenant isolation**: Check org_id in JWT matches embedded vectors
2. **Collection empty**: No vectors have been embedded yet
3. **Qdrant not running**: Check `docker compose ps qdrant`
4. **Filters too restrictive**: Remove asset_id/segment_id filters to test

**Debug**:

```bash
# Check Qdrant has vectors
curl http://localhost:6333/collections/embeddings

# Check job succeeded
curl http://localhost:8000/jobs/{job_id} \
  -H "Authorization: Bearer ..."
```

---

## What's Next

### Immediate Next Steps (Microstep 0.10+)

1. **Metrics & Observability** (HIGH PRIORITY):
   - Add Prometheus metrics for embedding/search latency
   - Add distributed tracing with OpenTelemetry
   - Create Grafana dashboards

2. **Reranking** (HIGH PRIORITY):
   - Add cross-encoder reranking for top-K results
   - Improves precision for semantic search

3. **Batch Processing** (MEDIUM PRIORITY):
   - Bulk embedding endpoint: `/vectors/embed/batch`
   - Process multiple texts in single job

4. **Vector Deletion** (MEDIUM PRIORITY):
   - Add deletion endpoints
   - Implement cleanup jobs for old vectors

5. **Advanced Filtering** (MEDIUM PRIORITY):
   - Date ranges, metadata filters
   - Hybrid search (semantic + BM25)

### Future Enhancements

- Multi-modal embeddings (images, audio)
- Fine-tuned models for domain-specific tasks
- Adaptive chunking strategies
- Vector quantization for faster search
- Federated search across multiple collections

---

## References

### Internal Documentation

- [Microstep 0.8: Qdrant Integration](./microstep-0.8-qdrant-integration.md)
- [Qdrant Developer Guide](./qdrant-developer-guide.md)
- [Architecture Overview](./architecture/overview.md)

### External Resources

- [SentenceTransformers Documentation](https://www.sbert.net/)
- [Qdrant Documentation](https://qdrant.tech/documentation/)
- [HuggingFace Model Hub](https://huggingface.co/models?library=sentence-transformers)

### Code References

| Component | File Path | Lines |
|-----------|-----------|-------|
| Adapter Protocol | `packages/common/src/heimdex_common/embeddings/adapter.py` | 13-54 |
| SentenceTransformer Adapter | `packages/common/src/heimdex_common/embeddings/adapters/sentence.py` | 15-114 |
| Factory + Registry | `packages/common/src/heimdex_common/embeddings/factory.py` | 20-173 |
| Worker Actor | `apps/worker/src/heimdex_worker/embeddings.py` | 50-350 |
| API Endpoints | `apps/api/src/heimdex_api/vectors.py` | 263-579 |
| Startup Validation | `apps/worker/src/heimdex_worker/__init__.py` | 44-94 |
| E2E Tests | `packages/common/tests/test_embeddings_e2e.py` | 1-500+ |

---

**Document Version**: 1.0
**Last Updated**: 2025-10-31
**Maintained By**: Heimdex Team
