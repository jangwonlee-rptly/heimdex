# Configuration

## Overview

Heimdex services use a centralized configuration system powered by Pydantic Settings. All configuration values are read from environment variables with sensible defaults for local development.

**Security Rule**: Configuration is loaded at process startup. Secrets are NEVER logged in plaintext - only redacted summaries appear in logs.

---

## Environment Variables

### Runtime Environment

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `HEIMDEX_ENV` | string | `local` | Deployment environment (`local`, `dev`, `staging`, `prod`) |
| `VERSION` | string | `0.0.0` | Service version (set by CI/CD in production) |

### PostgreSQL Connection

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `PGHOST` | string | `localhost` | PostgreSQL host (use service name `pg` in Docker Compose) |
| `PGPORT` | int | `5432` | PostgreSQL port |
| `PGUSER` | string | `heimdex` | PostgreSQL username |
| `PGPASSWORD` | string | `heimdex` | PostgreSQL password (**redacted in logs**) |
| `PGDATABASE` | string | `heimdex` | PostgreSQL database name |

**Connection URL**: The config layer automatically constructs SQLAlchemy-compatible URLs:
```
postgresql+psycopg2://heimdex:***@pg:5432/heimdex
```

### Redis Connection

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `REDIS_URL` | string | `redis://localhost:6379/0` | Full Redis connection URL (passwords redacted in logs) |

**Note**: Use service name `redis` in Docker Compose (`redis://redis:6379/0`).

### Qdrant Connection

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `QDRANT_URL` | string | `http://localhost:6333` | Qdrant HTTP API endpoint |

**Note**: Use service name `qdrant` in Docker Compose (`http://qdrant:6333`).

### GCS / Storage Connection

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `GCS_ENDPOINT` | string | `http://localhost:4443` | GCS-compatible storage endpoint (emulator or real GCS) |
| `GCS_BUCKET` | string | `heimdex-dev` | Target bucket name |
| `GCS_PROJECT_ID` | string | `heimdex-local` | GCS project ID |
| `GCS_USE_SSL` | bool | `false` | Use HTTPS for GCS connections (set `true` in prod) |
| `GOOGLE_APPLICATION_CREDENTIALS` | string | `null` | Path to service account JSON (optional for emulator) |

**Note**: For local development with the GCS emulator, set `STORAGE_EMULATOR_HOST=gcs:4443` to bypass authentication.

---

## Configuration Files

### Development: `.env` File

**Location**: Project root (`.env`)
**Status**: Git-ignored (never committed)

Example `.env` for local development:

```bash
# Runtime
HEIMDEX_ENV=local
VERSION=0.0.0-dev

# PostgreSQL
PGHOST=pg
PGPORT=5432
PGUSER=heimdex
PGPASSWORD=heimdex
PGDATABASE=heimdex

# Redis
REDIS_URL=redis://redis:6379/0

# Qdrant
QDRANT_URL=http://qdrant:6333

# GCS Emulator
GCS_ENDPOINT=http://gcs:4443
GCS_BUCKET=heimdex-dev
GCS_PROJECT_ID=heimdex-local
GCS_USE_SSL=false
STORAGE_EMULATOR_HOST=gcs:4443
```

### Production: Environment Variables

In production (Supabase, Cloud Run, etc.), set environment variables via the platform's secrets management:

- Supabase: Project Settings → Environment Variables
- Cloud Run: Secret Manager integration
- Docker Compose: `.env` file or `environment` blocks

**Critical**: NEVER commit production credentials to version control.

---

## Runtime Behavior

### Startup Sequence

1. **Load Configuration**: Pydantic Settings reads from environment variables
2. **Validate**: Ensure required values are present and valid (e.g., port in 1-65535 range)
3. **Log Summary**: Emit a single JSON log line with redacted config:
   ```json
   {
     "level": "INFO",
     "event": "starting",
     "service": "heimdex-api",
     "env": "local",
     "version": "0.0.0",
     "config": {
       "pghost": "pg",
       "pgport": "5432",
       "pguser": "***",
       "redis_url": "redis://***@redis:6379/0",
       "qdrant_url": "http://qdrant:6333",
       "gcs_endpoint": "http://gcs:4443"
     }
   }
   ```
4. **Fail Fast**: If critical config is missing/invalid, service exits with clear error

### Configuration Access

**From Application Code**:

```python
from heimdex_common.config import get_config

config = get_config()  # Singleton, loaded once per process
db_url = config.get_database_url()
```

**Redacted Logging**:

```python
log_event("INFO", "booting", config=config.log_summary(redact_secrets=True))
```

---

## Docker Compose Integration

### Service Names as Hostnames

Docker Compose creates an internal DNS network where service names resolve to container IPs:

| Service | Hostname | Port(s) |
|---------|----------|---------|
| PostgreSQL | `pg` | `5432` |
| Redis | `redis` | `6379` |
| Qdrant | `qdrant` | `6333`, `6334` (gRPC) |
| GCS Emulator | `gcs` | `4443` |
| API | `api` | `8000` |
| Worker | `worker` | N/A (background process) |

**Example**: API connects to PostgreSQL using `PGHOST=pg`, not `localhost`.

### Security: Internal Services

- PostgreSQL, Redis, Qdrant, GCS emulator: **no exposed ports** (internal only)
- API: **port 8000 exposed** to host (`localhost:8000`)
- Worker: **no exposed ports** (background daemon)

This prevents external access to infrastructure services in development.

---

## Runtime Rule: System Python in Containers

**Important**: Docker images install dependencies with `uv pip install --system`, and services run with system Python, NOT `uv run`.

**Why**: This ensures consistent dependency resolution and avoids uv virtual environment overhead in containers.

**In Dockerfiles**:
```dockerfile
RUN uv pip install --system -e packages/common -e apps/api
CMD ["uvicorn", "heimdex_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**NOT**:
```dockerfile
CMD ["uv", "run", "uvicorn", "..."]  # ❌ Do not use in containers
```

---

## Validation & Error Handling

### Fail-Fast Validation

Pydantic Settings performs validation at load time:

- **Missing Required**: `ValidationError` with clear message
- **Invalid Type**: E.g., `PGPORT=abc` raises `ValidationError`
- **Out-of-Range**: E.g., `PGPORT=99999` fails port range check (1-65535)

### Error Examples

**Missing PGHOST**:
```
pydantic.error_wrappers.ValidationError: 1 validation error for HeimdexConfig
PGHOST
  field required (type=value_error.missing)
```

**Invalid Port**:
```
ValueError: Invalid PostgreSQL port: 99999 (must be 1-65535)
```

**Solution**: Fix the environment variable and restart the service.

---

## Environment-Specific Behavior

| Environment | Log Level | Secrets in Logs | RLS Enabled | Migrations |
|-------------|-----------|----------------|-------------|------------|
| `local` | DEBUG | Redacted | No | Alembic (manual) |
| `dev` | INFO | Redacted | No | Alembic (CI) |
| `staging` | INFO | Redacted | Yes | Supabase SQL |
| `prod` | WARN | Redacted | Yes | Supabase SQL |

**RLS (Row-Level Security)**: Enforced in Supabase prod/staging via `org_id` scoping (future work).

---

## Testing Configuration

### Unit Tests

```python
from heimdex_common.config import reset_config, get_config

def test_custom_config():
    os.environ["PGHOST"] = "test-db"
    reset_config()  # Force reload
    config = get_config()
    assert config.pghost == "test-db"
```

### Integration Tests

Use a dedicated `.env.test` file:

```bash
export $(cat .env.test | xargs) && pytest
```

---

## Troubleshooting

### Config Not Loading

**Symptom**: Service uses default values despite setting env vars.

**Solution**:
1. Check `.env` file exists and is in the project root (for Docker Compose)
2. Verify `env_file: .env` in `docker-compose.yml`
3. Restart containers: `make down && make up`

### Redacted Logs Not Showing

**Symptom**: Can't see config summary in logs.

**Solution**:
1. Check `HEIMDEX_ENV` is set (logs may suppress in `prod`)
2. Look for `starting` event in structured logs:
   ```bash
   docker logs heimdex-api-1 | grep starting | jq .
   ```

### Connection Refused Errors

**Symptom**: `psycopg2.OperationalError: connection refused`.

**Solution**:
1. Ensure `PGHOST=pg` (not `localhost`) in Docker Compose
2. Verify `pg` service is running: `docker ps | grep pg`
3. Check readiness: `make readyz` (shows dependency probe status)

---

## References

- Pydantic Settings: https://docs.pydantic.dev/latest/concepts/pydantic_settings/
- SQLAlchemy Database URLs: https://docs.sqlalchemy.org/en/20/core/engines.html#database-urls
- Config Implementation: `packages/common/src/heimdex_common/config.py`
- Dependency Probes: `packages/common/src/heimdex_common/probes.py`
