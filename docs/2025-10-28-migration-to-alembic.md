# Migration to Alembic & Infrastructure Foundations

**Date**: 2025-10-28
**Micro-Step**: #0.5
**Status**: Implementation Complete, Testing Pending

---

## Overview

This document records the comprehensive changes made to introduce Alembic migrations, centralized configuration, and dependency probes to the Heimdex project. It serves as both a change log and a manual testing guide.

---

## Changes Made

### 1. Schema Migration to Alembic

**Problem**: Existing schema code used inline SQL with a `jobs` table (plural) that lacked fields for idempotency, org-scoping, and proper audit trails.

**Solution**:
- Created canonical SQLAlchemy models: `Job` (singular) and `JobEvent`
- Initialized Alembic migration system in `packages/common/`
- Generated initial migration: `001_job_ledger_init`
- Compiled SQL for Supabase: `supabase/migrations/0001_job_ledger_init.sql`

**Files Created**:
- `packages/common/src/heimdex_common/models.py` - SQLAlchemy ORM models
- `packages/common/alembic/` - Alembic migration infrastructure
- `packages/common/alembic/versions/001_job_ledger_init.py` - Initial migration
- `supabase/migrations/0001_job_ledger_init.sql` - Compiled SQL artifact

**Files Modified**:
- `packages/common/src/heimdex_common/db.py` - Replaced psycopg2-only code with SQLAlchemy session management
- `packages/common/pyproject.toml` - Added dependencies: sqlalchemy, alembic

**Breaking Change**: The old `jobs` table will be **dropped** when running the migration. This is intentional and safe in dev environments.

---

### 2. Centralized Configuration Management

**Problem**: Configuration was scattered across multiple files with hardcoded defaults and no validation.

**Solution**:
- Created `HeimdexConfig` Pydantic Settings class
- Centralized all environment variables (PG*, REDIS_URL, QDRANT_URL, GCS_*)
- Added validation (e.g., port range checks)
- Implemented redacted logging for secrets

**Files Created**:
- `packages/common/src/heimdex_common/config.py` - Configuration management

**Files Modified**:
- `apps/api/src/heimdex_api/main.py` - Startup logs config summary
- `apps/worker/src/heimdex_worker/main.py` - Startup logs config summary
- `packages/common/pyproject.toml` - Added dependencies: pydantic, pydantic-settings

**Breaking Change**: Services will now **fail fast** at startup if required environment variables are missing or invalid.

---

### 3. Dependency Health Probes

**Problem**: No way to verify that critical dependencies (PostgreSQL, Redis, Qdrant, GCS) were reachable before accepting traffic.

**Solution**:
- Implemented lightweight probes for each dependency
- Added `/readyz` endpoint to API with per-dependency timing
- Distinguished `/healthz` (liveness) from `/readyz` (readiness)

**Files Created**:
- `packages/common/src/heimdex_common/probes.py` - Dependency probe implementations

**Files Modified**:
- `apps/api/src/heimdex_api/main.py` - Added `/readyz` endpoint
- `packages/common/pyproject.toml` - Added dependencies: redis, requests, google-cloud-storage

**New Endpoints**:
- `GET /healthz` - Basic liveness check (always 200 if process alive)
- `GET /readyz` - Readiness check with dependency probes (503 if any dep down)

---

### 4. Developer Tooling

**Problem**: No easy way to run migrations or check readiness during development.

**Solution**:
- Added Makefile targets for common operations
- Created migration helper commands

**Files Modified**:
- `Makefile` - Added `migrate`, `makemigration`, `migration-history`, `readyz` targets

**New Commands**:
```bash
make migrate           # Run Alembic migrations
make makemigration     # Generate new migration
make migration-history # Show migration history
make readyz            # Check API readiness
```

---

### 5. Documentation

**Files Created**:
- `docs/db-schema.md` - Complete schema reference with audit trail
- `docs/configuration.md` - Environment variables and configuration guide
- `docs/2025-10-28-migration-to-alembic.md` - This file

**Files Modified**:
- `docs/architecture.md` - Updated schema section, added "Dependency Readiness" section

---

## Manual Testing Guide

### Prerequisites

1. **Docker Desktop running**
2. **Project dependencies installed** (will need to reinstall with new deps)
3. **Clean environment** (recommended: `make reset` to start fresh)

---

### Test 1: Verify Dependencies Installation

**Goal**: Ensure new Python packages are installed correctly.

**Steps**:
```bash
# 1. Navigate to project root
cd /Users/jangwonlee/Projects/heimdex

# 2. Install updated dependencies (using uv)
cd packages/common
uv pip install --system -e .

# 3. Verify imports work
python3 -c "from heimdex_common.models import Job, JobEvent; print('✅ Models import OK')"
python3 -c "from heimdex_common.config import get_config; print('✅ Config import OK')"
python3 -c "from heimdex_common.probes import probe_all_dependencies; print('✅ Probes import OK')"
```

**Expected Output**:
```
✅ Models import OK
✅ Config import OK
✅ Probes import OK
```

**Troubleshooting**:
- If imports fail, check that dependencies were added to `packages/common/pyproject.toml`
- Run `uv pip install --system sqlalchemy alembic pydantic pydantic-settings redis requests google-cloud-storage`

---

### Test 2: Verify Configuration Loading

**Goal**: Ensure config loads from environment variables and validates correctly.

**Steps**:
```bash
# 1. Test with default values (should work)
cd /Users/jangwonlee/Projects/heimdex
python3 -c "
from heimdex_common.config import get_config
config = get_config()
print('Environment:', config.environment)
print('PGHOST:', config.pghost)
print('Redis URL:', config.redis_url)
print('✅ Config loads with defaults')
"

# 2. Test validation (should fail with clear error)
PGPORT=99999 python3 -c "
from heimdex_common.config import get_config, reset_config
reset_config()
try:
    config = get_config()
    print('❌ Validation should have failed')
except ValueError as e:
    print('✅ Validation works:', str(e))
"

# 3. Test redacted logging
python3 -c "
from heimdex_common.config import get_config
config = get_config()
summary = config.log_summary(redact_secrets=True)
print('✅ Redacted config:', summary)
assert '***' in str(summary), 'Secrets should be redacted'
print('✅ Secrets are redacted')
"
```

**Expected Output**:
```
Environment: local
PGHOST: localhost
Redis URL: redis://localhost:6379/0
✅ Config loads with defaults

✅ Validation works: Invalid PostgreSQL port: 99999 (must be 1-65535)

✅ Redacted config: {'environment': 'local', 'version': '0.0.0', ...}
✅ Secrets are redacted
```

---

### Test 3: Verify Alembic Setup

**Goal**: Ensure Alembic can read the migration and show history.

**Steps**:
```bash
# 1. Show Alembic version
cd /Users/jangwonlee/Projects/heimdex/packages/common
alembic --version

# 2. Show migration history (should show 1 migration)
alembic history --verbose

# 3. Check current revision (should be empty before migration)
alembic current
```

**Expected Output**:
```
alembic 1.13.x

Rev: 001_job_ledger_init (head)
  Parent: <base>
  Path: .../alembic/versions/001_job_ledger_init.py

  Initial job ledger schema with job and job_event tables
  ...

Current revision(s) for postgresql://heimdex:***@localhost:5432/heimdex:
(empty) - no migrations run yet
```

**Troubleshooting**:
- If `alembic: command not found`, run `uv pip install --system alembic`
- If config errors occur, check `.env` file has `PGHOST`, `PGPORT`, etc.

---

### Test 4: Run Migration on Clean Database

**Goal**: Execute the Alembic migration and verify schema is created.

**Steps**:
```bash
# 1. Start Docker Compose services
cd /Users/jangwonlee/Projects/heimdex
make up

# Wait ~10 seconds for services to start

# 2. Check services are running
docker ps | grep -E 'pg|redis|qdrant|gcs'

# 3. Run the migration
cd packages/common
alembic upgrade head

# 4. Verify migration succeeded
alembic current

# 5. Connect to database and verify tables exist
docker exec -it $(docker ps -qf "name=pg") psql -U heimdex -d heimdex -c "\dt"

# 6. Check table structure
docker exec -it $(docker ps -qf "name=pg") psql -U heimdex -d heimdex -c "\d job"
docker exec -it $(docker ps -qf "name=pg") psql -U heimdex -d heimdex -c "\d job_event"
```

**Expected Output**:
```
INFO  [alembic.runtime.migration] Running upgrade  -> 001_job_ledger_init, Initial job ledger schema...

Current revision(s) for postgresql://heimdex:***@pg:5432/heimdex:
001_job_ledger_init (head)

           List of relations
 Schema |    Name    | Type  |  Owner
--------+------------+-------+---------
 public | job        | table | heimdex
 public | job_event  | table | heimdex

Table "public.job"
 Column               | Type                        | Nullable | Default
----------------------+-----------------------------+----------+-------------------
 id                   | uuid                        | not null | gen_random_uuid()
 org_id               | uuid                        | not null |
 type                 | character varying(100)      | not null |
 status               | character varying(50)       | not null | 'queued'::...
 ...
```

**Troubleshooting**:
- If `docker ps` shows no containers, run `make up` again
- If migration fails with "connection refused", wait 10 seconds and retry
- If tables already exist from old schema, run `make reset` to clean database
- If you see `jobs` table instead of `job`, the old schema still exists - the migration will drop it

---

### Test 5: Verify API Starts with New Config

**Goal**: Ensure API service boots successfully and logs redacted config.

**Steps**:
```bash
# 1. Check API container logs for startup message
docker logs $(docker ps -qf "name=api") | grep starting | tail -1

# 2. Verify config is logged (should show redacted values)
docker logs $(docker ps -qf "name=api") | grep starting | tail -1 | python3 -m json.tool

# 3. Check /healthz endpoint works
curl -s http://localhost:8000/healthz | python3 -m json.tool
```

**Expected Output**:
```json
{
  "ts": "2025-10-28T...",
  "service": "heimdex-api",
  "env": "local",
  "level": "INFO",
  "event": "starting",
  "config": {
    "environment": "local",
    "version": "0.0.0",
    "pghost": "pg",
    "pgport": "5432",
    "pguser": "***",
    "redis_url": "redis://***@redis:6379/0",
    "qdrant_url": "http://qdrant:6333",
    ...
  }
}

{
  "ok": true,
  "service": "heimdex-api",
  "version": "0.0.0",
  "env": "local",
  "started_at": "2025-10-28T..."
}
```

**Troubleshooting**:
- If API doesn't start, check logs: `docker logs $(docker ps -qf "name=api")`
- If config validation fails, check `.env` file or Docker Compose `environment` block
- If you see Python import errors, rebuild images: `docker-compose -f deploy/docker-compose.yml build api`

---

### Test 6: Verify Readiness Endpoint with Probes

**Goal**: Test `/readyz` endpoint returns dependency status.

**Steps**:
```bash
# 1. Check readiness with all dependencies up
make readyz

# 2. Check individual dependency status
curl -s http://localhost:8000/readyz | python3 -m json.tool | grep -A 3 '"deps"'

# 3. Test failure scenario: stop PostgreSQL
docker stop $(docker ps -qf "name=pg")

# 4. Check readiness again (should return 503)
curl -s -w "\nHTTP Status: %{http_code}\n" http://localhost:8000/readyz | python3 -m json.tool

# 5. Restart PostgreSQL
docker start $(docker ps -aqf "name=pg")

# Wait 5 seconds for PG to start
sleep 5

# 6. Verify readiness is green again
make readyz
```

**Expected Output** (Step 1):
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

**Expected Output** (Step 4, PostgreSQL down):
```json
{
  "ok": false,
  "service": "heimdex-api",
  "version": "0.0.0",
  "env": "local",
  "deps": {
    "pg": {"ok": false, "ms": 1003.45, "error": "connection refused or timeout"},
    "redis": {"ok": true, "ms": 5.67, "error": null},
    "qdrant": {"ok": true, "ms": 18.92, "error": null},
    "gcs": {"ok": true, "ms": 45.23, "error": null}
  }
}
HTTP Status: 503
```

**Troubleshooting**:
- If all probes fail, check services are running: `docker ps`
- If GCS probe fails with "bucket not found", this is expected if bucket wasn't created yet - it's safe to ignore in dev
- If probes timeout, increase timeout in `probes.py` or check service logs for issues

---

### Test 7: Verify Worker Starts with New Config

**Goal**: Ensure Worker service boots successfully.

**Steps**:
```bash
# 1. Check Worker container logs
docker logs $(docker ps -qf "name=worker") | grep starting | tail -1

# 2. Verify config is logged
docker logs $(docker ps -qf "name=worker") | grep starting | tail -1 | python3 -m json.tool

# 3. Verify worker is heartbeating
docker logs $(docker ps -qf "name=worker") | grep heartbeat | tail -3
```

**Expected Output**:
```json
{
  "ts": "2025-10-28T...",
  "service": "heimdex-worker",
  "env": "local",
  "level": "INFO",
  "event": "starting",
  "interval_seconds": 20,
  "config": {
    "environment": "local",
    "version": "0.0.0",
    "pghost": "pg",
    ...
  }
}

{"ts": "2025-10-28T...", "level": "INFO", "event": "heartbeat", ...}
{"ts": "2025-10-28T...", "level": "INFO", "event": "heartbeat", ...}
{"ts": "2025-10-28T...", "level": "INFO", "event": "heartbeat", ...}
```

---

### Test 8: Verify Existing Functionality Still Works

**Goal**: Ensure old job creation/status APIs still work (with caveats).

**Important Note**: The existing job endpoints (`POST /jobs`, `GET /jobs/{id}`) will **NOT work yet** because they reference the old `jobs` table which has been dropped. This is expected and will be fixed in the next micro-step (#0.6).

**Steps to verify infrastructure is healthy**:
```bash
# 1. Verify API is accepting requests
curl -s http://localhost:8000/healthz

# 2. Try creating a job (EXPECTED TO FAIL with clear error)
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"type": "mock_process"}'

# This will fail with a database error because the code still references "jobs" table
# Error message should mention table "jobs" does not exist

# 3. Verify database schema is correct
docker exec -it $(docker ps -qf "name=pg") psql -U heimdex -d heimdex -c "SELECT COUNT(*) FROM job"
```

**Expected Output**:
```json
{"ok": true, "service": "heimdex-api", ...}

{
  "detail": "Internal Server Error"
}
// Check logs: docker logs $(docker ps -qf "name=api") | tail -20
// Should show: psycopg2.errors.UndefinedTable: relation "jobs" does not exist

 count
-------
     0
(1 row)
```

**Why This Happens**:
The migration created the new `job` table, but the API code in `apps/api/src/heimdex_api/jobs.py` still references the old `jobs` table. This will be fixed in step #0.6 when we update the business logic to use the new schema.

**Verification**: The fact that the error says "relation 'jobs' does not exist" proves the migration worked - the old table is gone and the new `job` table exists.

---

## Rollback Plan

If you need to revert these changes:

### Option 1: Rollback Migration Only
```bash
cd packages/common
alembic downgrade base
```

This will drop the `job` and `job_event` tables.

### Option 2: Full Rollback with Git
```bash
# Stash or commit current work
git stash

# Reset to previous commit (before this work)
git log --oneline -10  # Find commit hash before changes
git reset --hard <commit-hash>

# Recreate old database
make reset
```

---

## Known Limitations / Future Work

1. **Job CRUD APIs not updated**: The existing `/jobs` endpoints will fail because they reference the old `jobs` table. This will be fixed in step #0.6.

2. **GCS bucket creation**: The GCS emulator bucket may not exist yet, causing probe failures. This is cosmetic and doesn't affect core functionality.

3. **No CI validation**: Migrations are not yet validated in CI. This will be added later.

4. **No RLS policies**: Row-Level Security policies for `org_id` are not yet applied. This will be added when deploying to Supabase.

5. **Dramatiq tasks not updated**: The worker tasks in `apps/worker/src/heimdex_worker/tasks.py` still reference the old `jobs` table. This will be fixed in step #0.6.

---

## Success Criteria

✅ All new Python modules import successfully
✅ Configuration loads and validates correctly
✅ Alembic shows migration history
✅ Migration creates `job` and `job_event` tables
✅ Old `jobs` table is dropped
✅ API starts and logs redacted config
✅ Worker starts and logs redacted config
✅ `/healthz` returns 200
✅ `/readyz` returns dependency status with timing
✅ Probes correctly detect dependency failures (503 when dep down)
✅ Makefile targets work (`make migrate`, `make readyz`)
✅ Documentation is complete and accurate

⚠️ **Expected Failure**: Job creation/status APIs fail with "table 'jobs' does not exist" (this is correct - will be fixed in #0.6)

---

## Next Steps (Micro-Step #0.6)

1. Update `apps/api/src/heimdex_api/jobs.py` to use new `job` table schema
2. Update `apps/worker/src/heimdex_worker/tasks.py` to use new `job` table schema
3. Implement job event logging in `job_event` table
4. Add `org_id` to job creation (hardcode a test UUID for now)
5. Test full job lifecycle: create → queue → process → complete
6. Verify job events are logged in `job_event` table

---

## Questions or Issues?

If you encounter problems during manual testing:

1. **Check logs first**: `docker logs $(docker ps -qf "name=api")` or `docker logs $(docker ps -qf "name=worker")`
2. **Verify services are running**: `docker ps` should show pg, redis, qdrant, gcs, api, worker
3. **Check database state**: `docker exec -it $(docker ps -qf "name=pg") psql -U heimdex -d heimdex`
4. **Reset everything**: `make reset` to start fresh
5. **Check dependencies**: Ensure new Python packages are installed

---

**Document Prepared By**: Claude Code
**Implementation Date**: 2025-10-28
**Review Status**: Pending Manual Testing
