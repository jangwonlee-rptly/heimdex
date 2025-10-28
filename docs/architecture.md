# Heimdex Architecture Overview

Heimdex orchestrates a pipeline that ingests customer-owned video libraries, extracts structured intelligence, and exposes tenant-scoped semantic search without moving the original assets. The platform relies on Supabase for authentication and access control, a FastAPI service for coordination, a Redis/Dramatiq worker tier for heavy processing, and specialized stores (Postgres, Qdrant, MinIO/S3) to retain derived insights.

```
Customer Drive → Ingestion Trigger → FastAPI API → Redis/Dramatiq queue → Worker
      ↓                                         ↓                        ↓
 Original video (unaltered)     Structured metadata → Postgres         Vector embeddings → Qdrant
                                                                  Sidecar JSON + media → MinIO/S3
```

## Async Job Processing Pattern

Heimdex uses **Dramatiq** with Redis as the message broker to handle long-running, multi-stage jobs asynchronously. This pattern is critical for video processing operations that can take minutes to complete.

### Why Dramatiq?

- **Reliability**: Built-in retry logic with exponential backoff
- **Durability**: Job state persists in Postgres, survives Redis restarts
- **Scalability**: Horizontal scaling via `docker-compose up --scale worker=N`
- **Observability**: Structured logging at every stage transition

### Job Lifecycle

1. **API receives request** → Creates job record in Postgres (status: `pending`)
2. **Job queued** → Dramatiq sends task to Redis
3. **Worker picks up task** → Updates status to `processing`, tracks progress
4. **Multi-stage execution** → Each stage updates `stage` and `progress` fields
5. **Completion** → Final result written to `result` JSONB field, status: `completed`
6. **Failure handling** → Automatic retries (up to 3), exponential backoff, dead-letter queue

### Database Schema

Jobs table tracks all async work:
- `id` (UUID): Unique job identifier
- `status` (VARCHAR): `pending` | `processing` | `completed` | `failed`
- `stage` (VARCHAR): Current processing stage (e.g., `extracting`, `analyzing`)
- `progress` (INTEGER): 0-100 percentage
- `result` (JSONB): Final output data
- `error` (TEXT): Error message if failed
- `created_at`, `updated_at` (TIMESTAMP): Audit trail

### Retry Strategy

Configured in `@dramatiq.actor` decorator:
- **max_retries**: 3 attempts
- **min_backoff**: 1000ms (1 second)
- **max_backoff**: 60000ms (1 minute)

After exhausting retries, jobs move to Redis dead-letter queue for manual inspection.

## Health & Operations

- API service exposes `/healthz` returning static metadata (service, version, environment, boot timestamp) to satisfy orchestration health probes without leaking infrastructure details.
- Worker service runs Dramatiq process with configurable concurrency (1 process, 2 threads by default).
- Both services log exclusively in single-line JSON with `ts`, `service`, `env`, `version`, `level`, and `msg` to keep observability tooling uniform.
- Docker healthchecks monitor HTTP readiness for the API, database connectivity for Postgres, and process liveness for workers.
