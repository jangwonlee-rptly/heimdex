# Qdrant Developer Quick Reference

**Audience**: Developers working with Heimdex vector embeddings
**Last Updated**: 2025-10-30

---

## Quick Start (5 Minutes)

### 1. Start Services

```bash
cd deploy
docker compose up -d
```

Wait for services to be healthy (~10 seconds):

```bash
curl http://localhost:8000/readyz | jq '.ready'
# Should return: true
```

### 2. Create Test Embedding

```bash
# Get dev token (for local testing only!)
TOKEN=$(python3 -c '
import sys; sys.path.insert(0, "../packages/common/src")
from heimdex_common.auth import create_dev_token
print(create_dev_token("dev-user", "550e8400-e29b-41d4-a716-446655440000"))
')

# Create mock embedding
curl -X POST http://localhost:8000/vectors/mock \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "asset_id": "my-doc",
    "segment_id": "chunk-0"
  }' | jq

# Response:
# {
#   "job_id": "abc-123-...",
#   "asset_id": "my-doc",
#   "segment_id": "chunk-0"
# }
```

### 3. Check Job Status

```bash
JOB_ID="<from-above>"
curl http://localhost:8000/jobs/$JOB_ID \
  -H "Authorization: Bearer $TOKEN" | jq

# Response:
# {
#   "id": "abc-123-...",
#   "status": "completed",  # or "pending", "processing", "failed"
#   "progress": 100,
#   "result": {
#     "point_id": "753ee532-60b1-4aa4-dc7d-4fb151e78483",
#     "vector_size": 384,
#     ...
#   }
# }
```

### 4. Query Qdrant Directly

```bash
# Check collection
curl http://localhost:6333/collections/embeddings | jq

# Get point by ID
POINT_ID="753ee532-60b1-4aa4-dc7d-4fb151e78483"
curl "http://localhost:6333/collections/embeddings/points/$POINT_ID" | jq
```

**Done!** You now have a working vector in Qdrant.

---

## Common Tasks

### Create Embedding (Mock)

**POST /vectors/mock**

```bash
curl -X POST http://localhost:8000/vectors/mock \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "asset_id": "doc-123",
    "segment_id": "chunk-0"
  }'
```

**Response**:

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "asset_id": "doc-123",
  "segment_id": "chunk-0"
}
```

**Notes**:

- Mock endpoint uses deterministic random vectors (not real embeddings)
- Same asset_id + segment_id → same vector every time
- Returns immediately; processing happens async

### Poll Job Status

**GET /jobs/{job_id}**

```bash
curl http://localhost:8000/jobs/$JOB_ID \
  -H "Authorization: Bearer $TOKEN"
```

**Response**:

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "stage": "completed",
  "progress": 100,
  "result": {
    "point_id": "753ee532-60b1-4aa4-dc7d-4fb151e78483",
    "collection": "embeddings",
    "vector_size": 384,
    "org_id": "550e8400-e29b-41d4-a716-446655440000",
    "asset_id": "doc-123",
    "segment_id": "chunk-0",
    "completed_at": "2025-10-30T08:34:48.049057+00:00"
  },
  "error": null,
  "created_at": "2025-10-30T08:34:45.123456+00:00",
  "updated_at": "2025-10-30T08:34:48.123456+00:00"
}
```

**Job Status Values**:

- `pending`: Waiting to start
- `processing`: Worker is processing
- `completed`: Success
- `failed`: Error occurred (check `error` field)

### Check Service Health

**GET /readyz**

```bash
curl http://localhost:8000/readyz | jq
```

**Response**:

```json
{
  "service": "api",
  "ready": true,
  "summary": "ok",
  "deps": {
    "pg": {"enabled": true, "ok": true, "latency_ms": 3.5},
    "redis": {"enabled": true, "ok": true, "latency_ms": 0.8},
    "qdrant": {"enabled": false, "skipped": true, "ok": null}
  }
}
```

**Note**: `qdrant` is disabled by default (`ENABLE_QDRANT=false`). Set to `true` in production.

### View Worker Logs

```bash
# Follow logs
docker compose logs worker -f

# Last 50 lines
docker compose logs worker --tail=50

# Grep for errors
docker compose logs worker | grep ERROR
```

### Direct Qdrant Operations

#### List Collections

```bash
curl http://localhost:6333/collections | jq
```

#### Get Collection Info

```bash
curl http://localhost:6333/collections/embeddings | jq
```

#### Retrieve Point by ID

```bash
curl "http://localhost:6333/collections/embeddings/points/753ee532-60b1-4aa4-dc7d-4fb151e78483" | jq
```

#### Search (Manual)

```bash
# Generate mock vector first, then search
curl -X POST http://localhost:6333/collections/embeddings/points/search \
  -H "Content-Type: application/json" \
  -d '{
    "vector": [0.1, 0.2, ...],  # 384 floats
    "limit": 10
  }' | jq
```

---

## Code Examples

### Python: Create Embedding

```python
import requests
from heimdex_common.auth import create_dev_token

# Get token
token = create_dev_token("user-123", "550e8400-e29b-41d4-a716-446655440000")
headers = {"Authorization": f"Bearer {token}"}

# Create embedding
response = requests.post(
    "http://localhost:8000/vectors/mock",
    headers=headers,
    json={
        "asset_id": "doc-123",
        "segment_id": "chunk-0"
    }
)

job_data = response.json()
job_id = job_data["job_id"]
print(f"Job created: {job_id}")
```

### Python: Wait for Job Completion

```python
import time

def wait_for_job(job_id, timeout=60):
    """Poll job until completion or timeout."""
    start = time.time()

    while time.time() - start < timeout:
        response = requests.get(
            f"http://localhost:8000/jobs/{job_id}",
            headers=headers
        )
        job = response.json()

        if job["status"] == "completed":
            return job["result"]
        elif job["status"] == "failed":
            raise Exception(f"Job failed: {job['error']}")

        time.sleep(1)

    raise TimeoutError(f"Job {job_id} did not complete in {timeout}s")

# Use it
result = wait_for_job(job_id)
print(f"Point ID: {result['point_id']}")
```

### Python: Use Qdrant Repository Directly

```python
from heimdex_common.vector import (
    ensure_collection,
    point_id_for,
    upsert_point,
    search
)
from heimdex_common.config import get_config

# Get config
config = get_config()

# Ensure collection exists
ensure_collection("embeddings", vector_size=384, distance="Cosine")

# Generate point ID
point_id = point_id_for(
    org_id="550e8400-e29b-41d4-a716-446655440000",
    asset_id="doc-123",
    segment_id="chunk-0",
    model="mock",
    model_ver="v1"
)
print(f"Point ID: {point_id}")

# Upsert vector
vector = [0.1] * 384  # Mock vector
payload = {
    "org_id": "550e8400-e29b-41d4-a716-446655440000",
    "asset_id": "doc-123",
    "segment_id": "chunk-0",
    "model": "mock",
    "text": "Example text"
}

upsert_point("embeddings", point_id, vector, payload)
print("Upserted!")

# Search
results = search("embeddings", vector, limit=5)
for r in results:
    print(f"ID: {r['id']}, Score: {r['score']}, Asset: {r['payload']['asset_id']}")
```

### TypeScript/JavaScript: Create Embedding

```typescript
// Using fetch
const token = "..."; // Get from auth

const response = await fetch("http://localhost:8000/vectors/mock", {
  method: "POST",
  headers: {
    "Authorization": `Bearer ${token}`,
    "Content-Type": "application/json"
  },
  body: JSON.stringify({
    asset_id: "doc-123",
    segment_id: "chunk-0"
  })
});

const { job_id } = await response.json();
console.log(`Job created: ${job_id}`);
```

### cURL: Full Workflow

```bash
#!/bin/bash
set -e

# 1. Get token
TOKEN=$(python3 -c 'import sys; sys.path.insert(0, "../packages/common/src"); from heimdex_common.auth import create_dev_token; print(create_dev_token("user", "550e8400-e29b-41d4-a716-446655440000"))')

# 2. Create embedding
RESPONSE=$(curl -s -X POST http://localhost:8000/vectors/mock \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"asset_id": "doc-123", "segment_id": "chunk-0"}')

JOB_ID=$(echo $RESPONSE | jq -r '.job_id')
echo "Job ID: $JOB_ID"

# 3. Poll until complete
while true; do
  STATUS=$(curl -s http://localhost:8000/jobs/$JOB_ID \
    -H "Authorization: Bearer $TOKEN" | jq -r '.status')

  echo "Status: $STATUS"

  if [ "$STATUS" = "completed" ]; then
    break
  elif [ "$STATUS" = "failed" ]; then
    echo "Job failed!"
    exit 1
  fi

  sleep 1
done

# 4. Get result
curl -s http://localhost:8000/jobs/$JOB_ID \
  -H "Authorization: Bearer $TOKEN" | jq '.result'
```

---

## Troubleshooting

### "Job stuck in pending"

**Check**: Outbox dispatcher running?

```bash
docker compose logs api | grep outbox_dispatcher
# Should see: "outbox_dispatcher_started"
```

**Check**: Worker running?

```bash
docker compose ps worker
# Should show: "Up" status
```

**Check**: Outbox table

```bash
docker compose exec pg psql -U heimdex -c "SELECT id, task_name, sent_at FROM outbox ORDER BY created_at DESC LIMIT 5;"
```

### "Job failed with Qdrant error"

**Check**: Qdrant service healthy?

```bash
docker compose ps qdrant
# Should show: "Up (healthy)"

curl http://localhost:6333/
# Should return: {"title":"qdrant - vector search engine","version":"1.11.3"}
```

**Check**: Worker logs

```bash
docker compose logs worker --tail=50 | grep ERROR
```

Common errors:

- `Connection refused`: Qdrant not running
- `Collection not found`: Collection creation failed
- `Dimensionality mismatch`: VECTOR_SIZE config wrong

### "Invalid JWT token"

**Check**: Token not expired?

```bash
# Dev tokens expire in 1 hour
# Regenerate token
```

**Check**: Correct org_id?

```bash
# Token must have matching org_id
```

### "Point ID collision"

**Cause**: Two jobs with same (org_id, asset_id, segment_id, model, model_ver)

**Solution**: Change one of these parameters to make unique

### Performance Issues

**Check**: Worker CPU/memory

```bash
docker stats worker
```

**Check**: Qdrant resource usage

```bash
docker stats qdrant
```

**Optimize**:

- Batch multiple embeddings in single job
- Add GPU for faster inference (when using real models)
- Increase worker concurrency

---

## Environment Variables

### Required

```bash
QDRANT_URL=http://qdrant:6333
VECTOR_SIZE=384
REDIS_URL=redis://redis:6379/0
PGHOST=pg
```

### Optional

```bash
# Enable Qdrant in health checks (default: false)
ENABLE_QDRANT=true

# Probe tuning
PROBE_TIMEOUT_MS=300
PROBE_RETRIES=2
PROBE_CACHE_SEC=10

# Worker concurrency (default: 2)
WORKER_CONCURRENCY=4

# Outbox dispatcher interval (default: 1000ms)
OUTBOX_DISPATCH_INTERVAL_MS=500
```

---

## Data Models

### Job

```typescript
{
  id: string;              // UUID
  status: "pending" | "processing" | "completed" | "failed";
  stage: string;           // Current processing stage
  progress: number;        // 0-100
  result: {                // Populated on success
    point_id: string;
    collection: string;
    vector_size: number;
    org_id: string;
    asset_id: string;
    segment_id: string;
    completed_at: string;  // ISO timestamp
  };
  error: string | null;    // Populated on failure
  created_at: string;      // ISO timestamp
  updated_at: string;      // ISO timestamp
}
```

### Qdrant Point

```typescript
{
  id: string;              // UUID from point_id_for()
  vector: number[];        // 384 floats (or VECTOR_SIZE)
  payload: {
    org_id: string;        // For tenant isolation
    asset_id: string;      // Source asset
    segment_id: string;    // Segment within asset
    model: string;         // "mock" or model name
    model_ver: string;     // "v1" etc
    text: string;          // (mock only) placeholder text
  }
}
```

---

## Best Practices

### 1. Always Use Job Polling

❌ **Don't** assume embedding is instant:

```python
response = requests.post("/vectors/mock", ...)
# Don't immediately assume it's done!
```

✅ **Do** poll job status:

```python
response = requests.post("/vectors/mock", ...)
job_id = response.json()["job_id"]
result = wait_for_job(job_id)  # Poll until complete
```

### 2. Handle Job Failures

❌ **Don't** ignore errors:

```python
job = get_job(job_id)
point_id = job["result"]["point_id"]  # Crashes if job failed!
```

✅ **Do** check status:

```python
job = get_job(job_id)
if job["status"] == "failed":
    logger.error(f"Job failed: {job['error']}")
    raise Exception(job["error"])
elif job["status"] == "completed":
    point_id = job["result"]["point_id"]
```

### 3. Use Idempotency

✅ **Safe** to retry:

```python
# Same parameters → same job_id
response1 = requests.post("/vectors/mock", json={"asset_id": "doc-1", "segment_id": "chunk-0"})
response2 = requests.post("/vectors/mock", json={"asset_id": "doc-1", "segment_id": "chunk-0"})

assert response1.json()["job_id"] == response2.json()["job_id"]
```

### 4. Scope by org_id

❌ **Don't** search across all orgs:

```python
# Missing org_id filter!
results = search("embeddings", query_vector, limit=10)
```

✅ **Do** filter by org_id:

```python
from qdrant_client.models import Filter, FieldCondition, MatchValue

query_filter = Filter(must=[
    FieldCondition(key="org_id", match=MatchValue(value=ctx.org_id))
])

results = search("embeddings", query_vector, limit=10, query_filter=query_filter)
```

### 5. Monitor Resource Usage

✅ **Track** Qdrant metrics:

```bash
# Collection size
curl http://localhost:6333/collections/embeddings | jq '.result.points_count'

# Memory usage
docker stats qdrant --no-stream

# Search latency
curl -w "Time: %{time_total}s\n" -X POST http://localhost:6333/collections/embeddings/points/search -d '...'
```

---

## Further Reading

- [Full Documentation](microstep-0.8-qdrant-integration.md)
- [Production Migration Guide](qdrant-mock-to-production.md)
- [Production TODOs](qdrant-production-todos.md)
- [Qdrant Official Docs](https://qdrant.tech/documentation/)

---

## Quick Links

- **Qdrant UI**: <http://localhost:6333/dashboard>
- **API Docs**: <http://localhost:8000/docs>
- **Health Check**: <http://localhost:8000/readyz>
- **Grafana** (if deployed): <http://localhost:3000>

---

**Questions?** Ask in #heimdex-engineering or file an issue.
