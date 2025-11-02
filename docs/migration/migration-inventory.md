# Database Migration Inventory

**Migration Date**: 2025-10-29
**Migration Type**: psycopg2 → SQLAlchemy ORM
**Status**: In Progress

## Executive Summary

This document tracks the complete migration from raw psycopg2 database connections to SQLAlchemy ORM. The migration involves:

- **3 files** with active psycopg2 database operations
- **1 file** with health probe using psycopg2 (will remain for lightweight probing)
- **2 SQLAlchemy models** already defined (Job, JobEvent)
- **1 Alembic migration** already created and ready to deploy

## Critical Finding: Infrastructure Already Exists! 🎉

**Good News**: The SQLAlchemy infrastructure is **already set up**:

- ✅ SQLAlchemy models defined in `packages/common/src/heimdex_common/models.py`
- ✅ Database session management in `packages/common/src/heimdex_common/db.py`
- ✅ Alembic migrations configured in `packages/common/alembic/`
- ✅ Configuration system in place with `heimdex_common/config.py`

**Current State**: The codebase has **BOTH** old psycopg2 code and new SQLAlchemy infrastructure side-by-side. The old `jobs` table is still being used by the application code, but new `job` and `job_event` tables are defined and ready.

## Files Requiring Migration

### 1. apps/api/src/heimdex_api/jobs.py ⚠️ HIGH PRIORITY

**Status**: ❌ Not migrated
**Database Operations**:

- Line 97-104: INSERT job (psycopg2, raw SQL, old `jobs` table)
- Line 137-146: SELECT job by ID (psycopg2, RealDictCursor, old `jobs` table)

**Migration Complexity**: MEDIUM

- 2 endpoints to migrate
- Direct queries → Repository pattern
- Uses old `jobs` table → needs to use new `job` table
- Returns Pydantic models (easy to adapt)

**Old Schema Mismatch**:

- Old: `(id, status, stage, progress, created_at, updated_at)`
- New: Adds `org_id, type, attempt, priority, idempotency_key, requested_by, started_at, finished_at, last_error_code, last_error_message`
- **Action Required**: Update INSERT to include required fields (`org_id`, `type`)

### 2. apps/worker/src/heimdex_worker/tasks.py ⚠️ HIGH PRIORITY

**Status**: ❌ Not migrated
**Database Operations**:

- Line 52-78: `_update_job_status()` function - Dynamic UPDATE (psycopg2, raw SQL, old `jobs` table)

**Migration Complexity**: MEDIUM

- 1 internal function called by Dramatiq actor
- Dynamic SQL construction → SQLAlchemy update patterns
- Uses old `jobs` table → needs to use new `job` table
- Uses `result = %s::jsonb` → needs JSONB handling

**Current Behavior**:

- Updates: status, stage, progress, result (JSONB), error
- Always updates `updated_at`
- Uses string formatting for dynamic SET clause (safe, uses parameterization)

### 3. packages/common/src/heimdex_common/probes.py ✅ KEEP AS-IS

**Status**: ✅ Intentional psycopg2 usage
**Database Operations**:

- Line 44-62: `probe_postgres()` - Health check with SELECT 1

**Migration Decision**: **NO MIGRATION NEEDED**

- **Rationale**: Lightweight health probes should not use ORM overhead
- **Best Practice**: Direct psycopg2 connection for liveness/readiness checks
- **Action**: Keep as-is, document as intentional exception

## Database Schema Analysis

### Existing Tables (Currently Used by App)

#### Table: `jobs` (plural, old schema)

**Columns**:

- `id` UUID PRIMARY KEY
- `status` VARCHAR
- `stage` VARCHAR (nullable)
- `progress` INTEGER
- `result` JSONB (nullable)
- `error` TEXT (nullable)
- `created_at` TIMESTAMPTZ
- `updated_at` TIMESTAMPTZ

**Indexes**:

- `idx_jobs_status` on `status`
- `idx_jobs_created_at` on `created_at`

### New Tables (Defined but Not Yet Used)

#### Table: `job` (singular, new schema)

**Defined in**: `packages/common/src/heimdex_common/models.py:29-170`
**Migration**: `packages/common/alembic/versions/001_job_ledger_init.py`

**Columns** (see db-schema.md for full details):

- `id` UUID PRIMARY KEY
- `org_id` UUID NOT NULL (NEW - for multi-tenancy)
- `type` VARCHAR(100) NOT NULL (NEW - job type discriminator)
- `status` VARCHAR(50) NOT NULL DEFAULT 'queued'
- `attempt` INTEGER NOT NULL DEFAULT 0 (NEW - retry counter)
- `priority` INTEGER NOT NULL DEFAULT 0 (NEW - future use)
- `idempotency_key` VARCHAR(255) (NEW - deduplication)
- `requested_by` VARCHAR(255) (NEW - attribution)
- `created_at` TIMESTAMPTZ NOT NULL
- `updated_at` TIMESTAMPTZ NOT NULL
- `started_at` TIMESTAMPTZ (NEW - execution timing)
- `finished_at` TIMESTAMPTZ (NEW - execution timing)
- `last_error_code` VARCHAR(100) (NEW - structured errors)
- `last_error_message` TEXT (NEW - replaces old `error`)

**Relationships**:

- One-to-many with `job_event` table

**Constraints**:

- Unique: `(org_id, idempotency_key)` WHERE idempotency_key IS NOT NULL
- Check: status IN ('queued', 'running', 'succeeded', 'failed', 'canceled', 'dead_letter')

**Indexes**:

- `idx_job_org_status` on `(org_id, status, created_at)`
- `idx_job_type_status` on `(type, status)`

#### Table: `job_event` (new, audit log)

**Defined in**: `packages/common/src/heimdex_common/models.py:172-237`
**Migration**: `packages/common/alembic/versions/001_job_ledger_init.py`

**Purpose**: Immutable audit log for job state transitions

**Columns**:

- `id` UUID PRIMARY KEY
- `job_id` UUID FOREIGN KEY → job.id (CASCADE DELETE)
- `ts` TIMESTAMPTZ NOT NULL
- `prev_status` VARCHAR(50) (nullable for initial state)
- `next_status` VARCHAR(50) NOT NULL
- `detail_json` JSONB (nullable, stores stage/progress/error details)

**Indexes**:

- `idx_job_event_job_ts` on `(job_id, ts)`
- `idx_job_event_ts` on `ts`

## Schema Mapping: Old → New

### Field Mapping

| Old Field | New Field(s) | Notes |
|-----------|--------------|-------|
| `id` | `id` | No change (UUID) |
| `status` | `status` | Values change: "pending"→"queued", "processing"→"running", "completed"→"succeeded" |
| `stage` | ❌ Removed | Move to `job_event.detail_json['stage']` |
| `progress` | ❌ Removed | Move to `job_event.detail_json['progress']` |
| `result` | ❌ Removed | Move to `job_event.detail_json` on terminal state |
| `error` | `last_error_code` + `last_error_message` | Split into structured fields |
| `created_at` | `created_at` | No change |
| `updated_at` | `updated_at` | No change |
| ❌ N/A | `org_id` | **NEW - Required**: Use default UUID for now |
| ❌ N/A | `type` | **NEW - Required**: Use "mock_process" for existing jobs |
| ❌ N/A | `attempt` | **NEW**: Default 0 |
| ❌ N/A | `priority` | **NEW**: Default 0 |
| ❌ N/A | `idempotency_key` | **NEW**: NULL for now |
| ❌ N/A | `requested_by` | **NEW**: NULL for now |
| ❌ N/A | `started_at` | **NEW**: NULL for now (set when status → running) |
| ❌ N/A | `finished_at` | **NEW**: NULL for now (set when terminal state) |

### Status Value Mapping

| Old Status | New Status |
|------------|------------|
| `pending` | `queued` |
| `processing` | `running` |
| `completed` | `succeeded` |
| `failed` | `failed` |

## Migration Phases (UPDATED based on existing infrastructure)

### ✅ Phase 1: Discovery and Audit (COMPLETE)

- ✅ Identify all psycopg2 usage
- ✅ Catalog database schema (old vs. new)
- ✅ Create migration inventory (this document)
- ✅ Verify SQLAlchemy infrastructure exists

### Phase 2: Repository Layer Implementation (NEW)

**Why needed**: Application code should not use models directly

**Tasks**:

1. Create `packages/common/src/heimdex_common/repositories/` directory
2. Create `job_repository.py` with JobRepository class
3. Implement methods:
   - `create_job(org_id, type, **kwargs)` → Job
   - `get_job_by_id(job_id)` → Job | None
   - `update_job_status(job_id, **kwargs)` → None
   - `log_job_event(job_id, prev_status, next_status, detail_json)` → JobEvent
4. Export repository in `__init__.py`

### Phase 3: Migrate API Endpoints

**File**: `apps/api/src/heimdex_api/jobs.py`

**Steps**:

1. Remove psycopg2 imports
2. Add SQLAlchemy imports (Session, models, repositories)
3. Update `create_job()`:
   - Replace raw INSERT with `JobRepository.create_job()`
   - Add required fields: `org_id` (default UUID), `type="mock_process"`
   - Remove `stage=None` (not in new schema)
   - Update status: "pending" → "queued"
   - Log initial job event
4. Update `get_job_status()`:
   - Replace raw SELECT with `JobRepository.get_job_by_id()`
   - Handle missing fields (stage, progress, result) from job_event if needed
   - Update status mapping in response

### Phase 4: Migrate Worker Tasks

**File**: `apps/worker/src/heimdex_worker/tasks.py`

**Steps**:

1. Remove psycopg2 imports
2. Add SQLAlchemy imports
3. Refactor `_update_job_status()`:
   - Replace raw UPDATE with `JobRepository.update_job_status()`
   - Handle `stage` and `progress`: store in job_event.detail_json
   - Handle `result`: store in job_event.detail_json on terminal state
   - Handle `error`: split into `last_error_code` + `last_error_message`
   - Log job event for every status change
4. Update `process_mock()`:
   - Update status values: "processing" → "running", "completed" → "succeeded"
   - Log job events at each stage transition
   - Set `started_at` when entering "running" state
   - Set `finished_at` when entering terminal state

### Phase 5: Deploy Schema Migration

**Tasks**:

1. Review Alembic migration: `packages/common/alembic/versions/001_job_ledger_init.py`
2. Run migration: `alembic upgrade head`
3. Verify new tables created: `job`, `job_event`
4. Verify old table dropped: `jobs`

### Phase 6: Testing and Validation

**Tasks**:

1. Create test suite:
   - Test job creation with new schema
   - Test job status queries
   - Test worker job processing
   - Test job event logging
   - Test error handling
2. Performance benchmarking:
   - Compare INSERT performance
   - Compare SELECT performance
   - Monitor connection pool usage
3. Integration testing:
   - Full flow: create → enqueue → process → query
   - Retry scenarios
   - Error scenarios

### Phase 7: Cleanup and Documentation

**Tasks**:

1. Remove all psycopg2 imports (except probes.py)
2. Update environment documentation
3. Generate MIGRATION_REPORT.md
4. Generate SQLALCHEMY_DEVELOPER_GUIDE.md
5. Update README with new database setup instructions

## Dependencies and Configuration

### Current Dependencies (packages/common/pyproject.toml)

```toml
psycopg2-binary>=2.9.9,<3.0.0  # Keep for probes
sqlalchemy>=2.0.0,<3.0.0        # Already present ✅
alembic>=1.13.0,<2.0.0          # Already present ✅
```

### Database Connection Configuration

**File**: `packages/common/src/heimdex_common/db.py`

**Current State**: ✅ Fully implemented with:

- `get_engine()` - SQLAlchemy engine with connection pooling
- `get_session_factory()` - Session factory
- `get_db()` - Context manager for transactional sessions
- Pool size: 5, Max overflow: 10
- Pool pre-ping: enabled

**Connection String**:

- Format: `postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}`
- Source: Environment variables (PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE)
- Managed by: `heimdex_common.config.HeimdexConfig`

## Migration Risks and Mitigations

### Risk 1: Schema Mismatch in Production

**Issue**: Old `jobs` table exists, new `job` table will be created
**Mitigation**: Alembic migration drops old table first (line 33 in 001_job_ledger_init.py)
**Status**: ✅ Handled

### Risk 2: Missing Required Fields (org_id, type)

**Issue**: New schema requires fields not in old INSERT statements
**Mitigation**:

- Use default `org_id = UUID('00000000-0000-0000-0000-000000000000')` for single-tenant
- Hardcode `type = "mock_process"` for existing job type
**Action**: Document these defaults in migration guide

### Risk 3: Status Value Changes

**Issue**: "pending" → "queued", "processing" → "running", "completed" → "succeeded"
**Mitigation**: Update all status strings in both API and Worker
**Action**: Use constants to prevent typos

### Risk 4: Loss of stage/progress/result Data

**Issue**: These fields removed from main `job` table
**Mitigation**: Store in `job_event.detail_json` instead
**Impact**: Queries for stage/progress require joining with job_event
**Action**: Repository methods should handle this transparently

### Risk 5: Performance Regression

**Issue**: ORM overhead vs. raw SQL
**Mitigation**:

- Use SQLAlchemy 2.0 style (faster)
- Connection pooling already configured
- Benchmark before/after
**Status**: Low risk (simple queries)

## Breaking Changes

### API Response Changes (Potential)

**Current**: `GET /jobs/{job_id}` returns:

```json
{
  "id": "...",
  "status": "processing",  // OLD VALUE
  "stage": "analyzing",     // FROM jobs.stage
  "progress": 50,           // FROM jobs.progress
  "result": {...},          // FROM jobs.result
  "error": "...",           // FROM jobs.error
  "created_at": "...",
  "updated_at": "..."
}
```

**New**: Same structure, but:

- `status`: Values change ("processing" → "running", etc.)
- `stage`: Fetched from latest job_event.detail_json
- `progress`: Fetched from latest job_event.detail_json
- `result`: Fetched from terminal job_event.detail_json
- `error`: Constructed from last_error_code + last_error_message

**Decision**: Maintain backward compatibility by mapping in Repository

## Rollback Plan

### If Migration Fails

1. Do NOT run `alembic upgrade head`
2. Keep old `jobs` table
3. Keep old psycopg2 code

### If Migration Succeeds but Issues Found

1. Stop API and Worker services
2. Run `alembic downgrade base` (drops new tables)
3. Manually recreate old `jobs` table using old schema
4. Revert code changes
5. Restart services

**Note**: Alembic migration does NOT preserve old data (drops old table). For production, would need data migration script first.

## Next Steps

1. ✅ Complete Phase 1 (this document)
2. 🔄 Implement Phase 2 (Repository layer)
3. 🔄 Implement Phase 3 (Migrate API)
4. 🔄 Implement Phase 4 (Migrate Worker)
5. 🔄 Execute Phase 5 (Deploy schema)
6. 🔄 Execute Phase 6 (Test and validate)
7. 🔄 Complete Phase 7 (Cleanup and docs)

## Progress Tracking

| Phase | Status | Files Modified | Tests Added | Completion Date |
|-------|--------|----------------|-------------|-----------------|
| 1. Discovery | ✅ Complete | 0 | 0 | 2025-10-29 |
| 2. Repository | ⏳ Pending | 0 | 0 | - |
| 3. API Migration | ⏳ Pending | 1 | 0 | - |
| 4. Worker Migration | ⏳ Pending | 1 | 0 | - |
| 5. Schema Deploy | ⏳ Pending | 0 | 0 | - |
| 6. Testing | ⏳ Pending | 0 | TBD | - |
| 7. Cleanup | ⏳ Pending | 2 | 0 | - |

**Total Files to Modify**: 4 (repository, API, Worker, cleanup)
**Total Tests to Create**: TBD (Phase 6)
**Estimated Completion**: After all phases complete

---

**Document Version**: 1.0
**Last Updated**: 2025-10-29
**Next Review**: After Phase 2 completion
