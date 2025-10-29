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

**Canonical schema** (managed by Alembic):

**`job` table** (durable ledger):
- `id` (UUID): Globally unique job identifier
- `org_id` (UUID): Organization/tenant identifier (for RLS in Supabase)
- `type` (VARCHAR): Job type discriminator (`mock_process`, `drive_ingest`, etc.)
- `status` (VARCHAR): `queued` | `running` | `succeeded` | `failed` | `canceled` | `dead_letter`
- `attempt` (INTEGER): Retry attempt counter (0 = first attempt)
- `priority` (INTEGER): Job priority (higher = more urgent, future use)
- `idempotency_key` (VARCHAR): Client-provided key for deduplication
- `requested_by` (VARCHAR): User/service that requested the job
- `created_at`, `updated_at`, `started_at`, `finished_at` (TIMESTAMPTZ): Lifecycle timestamps
- `last_error_code` (VARCHAR): Error classification (`TIMEOUT`, `VALIDATION_ERROR`, etc.)
- `last_error_message` (TEXT): Human-readable error detail

**`job_event` table** (immutable audit log):
- `id` (UUID): Unique event identifier
- `job_id` (UUID): Foreign key to `job.id`
- `ts` (TIMESTAMPTZ): Event occurrence timestamp
- `prev_status` (VARCHAR): Status before transition (NULL for initial state)
- `next_status` (VARCHAR): Status after transition
- `detail_json` (JSONB): Additional metadata (stage, progress, error details)

See `docs/db-schema.md` for full schema reference including indexes and constraints.

### Retry Strategy

Configured in `@dramatiq.actor` decorator:
- **max_retries**: 3 attempts
- **min_backoff**: 1000ms (1 second)
- **max_backoff**: 60000ms (1 minute)

After exhausting retries, jobs move to Redis dead-letter queue for manual inspection.

## Dependency Readiness

### Health vs. Readiness

**`/healthz`**: Basic liveness check (process running, responding)
- Returns static metadata: service name, version, environment, start time
- Always returns HTTP 200 if process is alive
- No dependency checks (fast, non-blocking)

**`/readyz`**: Comprehensive readiness check with dependency probes
- Probes all critical dependencies: PostgreSQL, Redis, Qdrant, GCS
- Returns HTTP 200 if all deps are healthy, HTTP 503 otherwise
- Includes per-dependency timing (milliseconds)
- Used by orchestrators (k8s, Cloud Run) to route traffic

### Probe Semantics

Each probe:
1. Performs a shallow health check (e.g., `SELECT 1` for PostgreSQL, `PING` for Redis)
2. Enforces a short timeout (default: 1000ms, GCS gets 2000ms for cold start)
3. Returns `{ok: bool, ms: float, error: string | null}`

**Failure Modes**:
- **Connection refused**: Dependency not reachable (wrong hostname, service down)
- **Timeout**: Dependency slow/overloaded (probe timeout exceeded)
- **Auth error**: Credentials invalid (check env vars)

### Readiness Response Example

```json
{
  "ok": true,
  "service": "heimdex-api",
  "version": "0.0.0",
  "env": "local",
  "deps": {
    "pg": {"ok": true, "ms": 12.34, "error": null},
    "redis": {"ok": true, "ms": 5.67, "error": null},
    "qdrant": {"ok": true, "ms": 18.92, "error": null},
    "gcs": {"ok": true, "ms": 45.23, "error": null}
  }
}
```

If any dependency fails:
```json
{
  "ok": false,
  "service": "heimdex-api",
  "version": "0.0.0",
  "env": "local",
  "deps": {
    "pg": {"ok": false, "ms": 1003.45, "error": "connection timeout"},
    "redis": {"ok": true, "ms": 5.67, "error": null},
    "qdrant": {"ok": true, "ms": 18.92, "error": null},
    "gcs": {"ok": true, "ms": 45.23, "error": null}
  }
}
```
→ Returns **HTTP 503 Service Unavailable**

### Timeout Strategy

| Dependency | Timeout | Rationale |
|------------|---------|-----------|
| PostgreSQL | 1000ms | Low latency expected for local connections |
| Redis | 1000ms | In-memory, should respond instantly |
| Qdrant | 1000ms | HTTP API, fast response expected |
| GCS | 2000ms | Emulator may have cold-start delay |

### Usage

- **Orchestration**: Configure k8s/Cloud Run readiness probes to poll `/readyz`
- **Manual debugging**: `make readyz` (formatted JSON output)
- **CI/CD**: Healthcheck script before running integration tests

## Health & Operations

- API service exposes `/healthz` for liveness and `/readyz` for dependency-aware readiness checks.
- Worker service runs Dramatiq process with configurable concurrency (1 process, 2 threads by default).
- Both services log exclusively in single-line JSON with `ts`, `service`, `env`, `version`, `level`, and `msg` to keep observability tooling uniform.
- Configuration is loaded at startup from environment variables and logged once (redacted) for auditability.
- Docker healthchecks monitor HTTP readiness for the API, database connectivity for Postgres, and process liveness for workers.
