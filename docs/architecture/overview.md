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
- `status` (`job_status` ENUM): `queued` | `running` | `succeeded` | `failed` | `canceled` | `dead_letter`
- `attempt` / `max_attempts` (INTEGER): Current retry count vs. retry budget before dead-lettering
- `backoff_policy` (`job_backoff_policy` ENUM): Retry policy (`none`, `fixed`, `exp`)
- `priority` (INTEGER): Job priority (higher = more urgent, future use)
- `idempotency_key` (VARCHAR): Client-provided key for deduplication (partial unique index on `(org_id, idempotency_key)` where non-null)
- `requested_by` (VARCHAR): User/service that requested the job
- `created_at`, `updated_at`, `started_at`, `finished_at` (TIMESTAMPTZ): Lifecycle timestamps
- `last_error_code` (VARCHAR(64)): Error classification (`TIMEOUT`, `VALIDATION_ERROR`, etc.)
- `last_error_message` (VARCHAR(2048)): Human-readable error detail (truncated on write)
- `ck_job__status_finished_at_consistency`: Enforces `finished_at` is present only for terminal states (`succeeded`, `failed`, `canceled`, `dead_letter`)

**`job_event` table** (immutable audit log):

- `id` (UUID): Unique event identifier
- `job_id` (UUID): Foreign key to `job.id`
- `ts` (TIMESTAMPTZ): Event occurrence timestamp
- `prev_status` (VARCHAR): Status before transition (NULL for initial state)
- `next_status` (VARCHAR): Status after transition
- `detail_json` (JSONB): Additional metadata (stage, progress, error details)

See `../migration/db-schema.md` for full schema reference including indexes and constraints.

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

**`/readyz`**: Profile-aware readiness check with dependency probes

- Probes **only enabled dependencies** (configured via `ENABLE_*` flags)
- Disabled dependencies are skipped and don't affect readiness
- Returns HTTP 200 if all enabled deps are healthy, HTTP 503 otherwise
- Includes per-dependency timing, retry counts, and failure reasons
- Used by orchestrators (k8s, Cloud Run) to route traffic

### Profile-Aware Behavior

**Current Compose Environment** (default flags):

- **Enabled**: PostgreSQL, Redis → affect readiness
- **Disabled**: Qdrant, GCS → skipped (not yet deployed)

When you add Qdrant to docker-compose (micro-step 0.8), set `ENABLE_QDRANT=true` to include it in readiness checks.

**Why Profile-Aware?**

- Prevents false negatives (no "503" errors for services that don't exist yet)
- Clean switch pattern: add service → flip flag → redeploy
- No code changes needed when adding dependencies

### Probe Semantics

Each enabled probe:

1. Performs a shallow health check (e.g., `SELECT 1` for PostgreSQL, `PING` for Redis)
2. Enforces a tight per-attempt timeout (default: 300ms)
3. Retries with jittered exponential backoff (default: 2 retries, 100-200ms backoff)
4. Caches successful results (10s) and failed results (30s cooldown) to prevent probe storms
5. Returns uniform structure:

   ```
   {
     enabled: bool,
     skipped: bool,
     ok: bool | null,
     latency_ms: float | null,
     attempts: int,
     reason: string | null
   }
   ```

**Failure Modes**:

- **Connection refused**: Dependency not reachable (wrong hostname, service down)
- **Timeout**: Dependency slow/overloaded (probe timeout exceeded)
- **Auth error**: Credentials invalid (check env vars)
- **Disabled**: Dependency not enabled (skipped, doesn't affect readiness)

### Readiness Response Examples

**Minimal Profile** (current: PG + Redis only):

```json
{
  "service": "api",
  "env": "local",
  "version": "0.0.0",
  "ready": true,
  "summary": "ok",
  "deps": {
    "pg": {
      "enabled": true,
      "skipped": false,
      "ok": true,
      "latency_ms": 2.1,
      "attempts": 1,
      "reason": null
    },
    "redis": {
      "enabled": true,
      "skipped": false,
      "ok": true,
      "latency_ms": 0.8,
      "attempts": 1,
      "reason": null
    },
    "qdrant": {
      "enabled": false,
      "skipped": true,
      "ok": null,
      "latency_ms": null,
      "attempts": 0,
      "reason": "disabled"
    },
    "gcs": {
      "enabled": false,
      "skipped": true,
      "ok": null,
      "latency_ms": null,
      "attempts": 0,
      "reason": "disabled"
    }
  }
}
```

→ Returns **HTTP 200 OK** (only PG and Redis checked)

**Full Profile** (future: all deps enabled):

```json
{
  "service": "api",
  "env": "local",
  "version": "0.0.0",
  "ready": true,
  "summary": "ok",
  "deps": {
    "pg": {"enabled": true, "skipped": false, "ok": true, "latency_ms": 2.1, "attempts": 1, "reason": null},
    "redis": {"enabled": true, "skipped": false, "ok": true, "latency_ms": 0.8, "attempts": 1, "reason": null},
    "qdrant": {"enabled": true, "skipped": false, "ok": true, "latency_ms": 15.3, "attempts": 1, "reason": null},
    "gcs": {"enabled": true, "skipped": false, "ok": true, "latency_ms": 42.7, "attempts": 1, "reason": null}
  }
}
```

**Failure Example** (Redis down):

```json
{
  "service": "api",
  "env": "local",
  "version": "0.0.0",
  "ready": false,
  "summary": "down",
  "deps": {
    "pg": {"enabled": true, "skipped": false, "ok": true, "latency_ms": 2.1, "attempts": 1, "reason": null},
    "redis": {
      "enabled": true,
      "skipped": false,
      "ok": false,
      "latency_ms": 300.4,
      "attempts": 3,
      "reason": "timeout"
    },
    "qdrant": {"enabled": false, "skipped": true, "ok": null, "latency_ms": null, "attempts": 0, "reason": "disabled"},
    "gcs": {"enabled": false, "skipped": true, "ok": null, "latency_ms": null, "attempts": 0, "reason": "disabled"}
  }
}
```

→ Returns **HTTP 503 Service Unavailable**

### Probe Tunables

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| `PROBE_TIMEOUT_MS` | 300 | 50-5000 | Per-attempt timeout (milliseconds) |
| `PROBE_RETRIES` | 2 | 0-5 | Number of retry attempts |
| `PROBE_COOLDOWN_SEC` | 30 | 5-300 | Cooldown after failure (seconds) |
| `PROBE_CACHE_SEC` | 10 | 1-60 | Cache duration for success (seconds) |

**Performance**: Tight defaults ensure fast failure detection. Typical healthy probe: <200ms total (including all retries).

**Caching**: Prevents probe storms by caching results. Successful probes cached for 10s, failed probes trigger 30s cooldown.

### Usage

- **Orchestration**: Configure k8s/Cloud Run readiness probes to poll `/readyz`
- **Manual debugging**: `curl http://localhost:8000/readyz | jq`
- **CI/CD**: Healthcheck script before running integration tests
- **Add new dependency**: Set `ENABLE_<DEP>=true` in `.env`, restart services

## Authentication & Tenancy

### JWT-Based Authentication

Heimdex uses JWT tokens for authentication with two modes:

**Dev Mode** (local development):

- Provider: `AUTH_PROVIDER=dev`
- Algorithm: HS256 (symmetric)
- Secret: Configured via `DEV_JWT_SECRET`
- **Security**: Automatically disabled when `HEIMDEX_ENV=prod`

**Supabase Mode** (production):

- Provider: `AUTH_PROVIDER=supabase`
- Algorithm: RS256 (asymmetric)
- Verification: Public keys from JWKS endpoint
- Required claims: `aud`, `iss`, `sub`, `org_id`

See [auth.md](./auth.md) for detailed documentation.

### Request Context

All authenticated API requests inject a `RequestContext`:

```python
@dataclass
class RequestContext:
    user_id: str      # From JWT 'sub' claim
    org_id: str       # From JWT custom claim
    role: str | None  # Optional role claim
```

**Usage in routes**:

```python
from heimdex_common.auth import RequestContext, verify_jwt

@router.post("/jobs")
async def create_job(
    request: JobCreateRequest,
    ctx: RequestContext = Depends(verify_jwt),
):
    # Automatically scoped to ctx.org_id
    job = repo.create_job(org_id=ctx.org_id, ...)
```

### Tenant Isolation

**Enforcement Strategy**:

1. **Creation**: Resources created with authenticated `org_id`
2. **Retrieval**: Cross-tenant access returns HTTP 403
3. **Queries**: Database queries filtered by `org_id`

**Example - Job Retrieval**:

```python
job = repo.get_job_by_id(job_id)

# Enforce tenant boundary
if str(job.org_id) != ctx.org_id:
    raise HTTPException(status_code=403, detail="Access denied")
```

**Future Enhancement**: Row-Level Security (RLS) in PostgreSQL for defense-in-depth.

### Organization Claim Locations

The middleware checks for `org_id` in order of precedence:

1. `app_metadata.org_id` (Supabase pattern)
2. `https://heimdex.io/org_id` (custom namespace)
3. `org_id` (direct claim)

**Supabase Configuration**:
Set `org_id` in user metadata via SQL trigger:

```sql
CREATE OR REPLACE FUNCTION set_org_id()
RETURNS TRIGGER AS $$
BEGIN
  NEW.raw_app_meta_data = jsonb_set(
    COALESCE(NEW.raw_app_meta_data, '{}'::jsonb),
    '{org_id}',
    to_jsonb(NEW.id::text)
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
```

## Health & Operations

- API service exposes `/healthz` for liveness and `/readyz` for dependency-aware readiness checks.
- Worker service runs Dramatiq process with configurable concurrency (1 process, 2 threads by default).
- Both services log exclusively in single-line JSON with `ts`, `service`, `env`, `version`, `level`, and `msg` to keep observability tooling uniform.
- Configuration is loaded at startup from environment variables and logged once (redacted) for auditability.
- Docker healthchecks monitor HTTP readiness for the API, database connectivity for Postgres, and process liveness for workers.
