# Database Schema

## Schema Audit & Reconciliation

### Existing Schema Discovery

**Date**: 2025-10-28
**Scope**: Complete repository scan for schema definitions, SQL, and model code

#### Files Found

1. **packages/common/src/heimdex_common/db.py** (lines 76-90)
   - Contains inline SQL CREATE TABLE statement
   - Table name: `jobs` (plural)
   - Columns: id (UUID), status, stage, progress, result (JSONB), error, created_at, updated_at
   - Indexes: idx_jobs_status, idx_jobs_created_at

2. **apps/api/src/heimdex_api/jobs.py** (lines 98-104, 138-145)
   - INSERT and SELECT operations on `jobs` table
   - Uses psycopg2 raw SQL queries
   - No SQLAlchemy models

3. **apps/worker/src/heimdex_worker/tasks.py** (lines 30-78)
   - UPDATE operations on `jobs` table
   - Dynamic SQL construction for job status updates
   - No SQLAlchemy models

#### Reconciliation Decisions

**Issue**: Existing table uses plural name `jobs`, but canonical naming convention prefers singular `job`.

**Decision**: **SUPERSEDE** - Create new canonical tables with the following rationale:

- New tables: `job` (singular) and `job_event` (new)
- The existing `jobs` table schema is incomplete for the durable ledger requirements
- Missing fields: org_id, type, attempt, priority, idempotency_key, requested_by, started_at, finished_at, last_error_code, last_error_message
- No event log table exists
- Migration path:
  - Create new `job` and `job_event` tables via Alembic
  - Drop old `jobs` table (safe in dev environment)
  - Update all code references from `jobs` to `job`

**Conflicts Identified**:

- Column naming: existing `error` (TEXT) vs. new `last_error_code` + `last_error_message` split
- Missing state machine audit trail (no event log)
- No org_id for multi-tenancy (RLS future requirement)
- No idempotency_key for deduplication

---

## Canonical Schema

### Table: `job`

The durable ledger for all asynchronous jobs in the system.

**Table Name**: `job` (singular)

#### Columns

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | UUID | NO | gen_random_uuid() | Primary key, globally unique job identifier |
| org_id | UUID | NO | - | Organization/tenant identifier (for future RLS) |
| type | VARCHAR(100) | NO | - | Job type discriminator (e.g., 'mock_process', 'drive_ingest') |
| status | `job_status` ENUM | NO | `'queued'` | Current job state (enum: queued, running, succeeded, failed, canceled, dead_letter) |
| attempt | INTEGER | NO | 0 | Retry attempt counter (0 = first attempt) |
| max_attempts | INTEGER | NO | 5 | Maximum retry attempts before dead-lettering |
| backoff_policy | `job_backoff_policy` ENUM | NO | `'exp'` | Retry backoff policy (`none`, `fixed`, `exp`) |
| priority | INTEGER | NO | 0 | Job priority (higher = more urgent, future use) |
| idempotency_key | VARCHAR(255) | YES | NULL | Client-provided key for deduplication |
| requested_by | VARCHAR(255) | YES | NULL | User/service that requested the job |
| created_at | TIMESTAMPTZ | NO | NOW() | Job creation timestamp |
| updated_at | TIMESTAMPTZ | NO | NOW() | Last modification timestamp |
| started_at | TIMESTAMPTZ | YES | NULL | When job execution started |
| finished_at | TIMESTAMPTZ | YES | NULL | When job reached terminal state |
| last_error_code | VARCHAR(64) | YES | NULL | Error classification (e.g., 'TIMEOUT', 'VALIDATION_ERROR') |
| last_error_message | VARCHAR(2048) | YES | NULL | Human-readable error detail (truncated in repository layer) |

#### Constraints

- **Primary Key**: `id`
- **Partial Unique Index**: `idx_job__org_id_idempotency_key` on `(org_id, idempotency_key)` WHERE `idempotency_key IS NOT NULL`
- **Status Enum**: enforced by `job_status` PostgreSQL enum
- **Finished Timestamp Check**: `ck_job__status_finished_at_consistency` enforces `finished_at` is set only for terminal states

#### Indexes

| Name | Columns | Type | Purpose |
|------|---------|------|---------|
| pk_job | id | PRIMARY KEY | Fast lookups by job ID |
| idx_job__job_org_id | (org_id) | BTREE | Fast lookups by tenant |
| idx_job__org_id_created_at_desc | (org_id, created_at DESC) | BTREE | Org-scoped chronological queries |
| idx_job__org_id_idempotency_key | (org_id, idempotency_key) WHERE `idempotency_key IS NOT NULL` | PARTIAL BTREE | Deduplication lookups |
| idx_job__status_created_at | (status, created_at) | BTREE | Operational monitoring by status |

#### State Machine

```
                   ┌─────────┐
                   │ queued  │ (initial)
                   └────┬────┘
                        │
                   ┌────▼────┐
             ┌────►│ running │◄────┐
             │     └────┬────┘     │
             │          │          │
             │          │          │
    (retry)  │     ┌────▼──────────▼───┐
             │     │                   │
             └─────┤  succeeded        │ (terminal)
             │     │  failed           │
             │     │  canceled         │
             │     │  dead_letter      │
             │     └───────────────────┘
             │              │
             └──────────────┘
                (max retries)
```

**States**:

- `queued`: Job created, waiting for worker pickup
- `running`: Worker actively processing
- `succeeded`: Completed successfully (terminal)
- `failed`: Encountered error, eligible for retry
- `canceled`: User/system canceled (terminal)
- `dead_letter`: Max retries exceeded (terminal)

**Transition Rules**:

- Retries: `failed` → `queued` (if attempt < max_retries)
- Max retries: `failed` → `dead_letter` (if attempt >= max_retries)
- Normal flow: `queued` → `running` → `succeeded`
- Error flow: `queued` → `running` → `failed` → (retry or dead_letter)

---

### Table: `job_event`

Immutable audit log of all job state transitions.

**Table Name**: `job_event` (singular)

#### Columns

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | UUID | NO | gen_random_uuid() | Primary key, unique event identifier |
| job_id | UUID | NO | - | Foreign key to job.id |
| ts | TIMESTAMPTZ | NO | NOW() | Event occurrence timestamp |
| prev_status | VARCHAR(50) | YES | NULL | Status before transition (NULL for initial state) |
| next_status | VARCHAR(50) | NO | - | Status after transition |
| detail_json | JSONB | YES | NULL | Additional event metadata (stage, progress, error details) |

#### Constraints

- **Primary Key**: `id`
- **Foreign Key**: `job_id` REFERENCES `job(id)` ON DELETE CASCADE

#### Indexes

| Name | Columns | Type | Purpose |
|------|---------|------|---------|
| pk_job_event | id | PRIMARY KEY | Fast lookups by event ID |
| idx_job_event__job_id_ts | (job_id, ts) | BTREE | Job timeline queries |
| idx_job_event__ts | (ts) | BTREE | Chronological event queries |

#### Rationale

- Immutable append-only log for compliance/debugging
- Enables job timeline reconstruction
- Separates hot operational data (job table) from cold audit data
- Supports future analytics (job duration, failure patterns, retry rates)

---

## Migration Strategy

### Phase 1: Alembic Setup (this PR)

1. Create `job` and `job_event` tables via Alembic migration
2. Drop existing `jobs` table (CREATE TABLE IF NOT EXISTS prevents conflicts)
3. Update all application code to use new schema

### Phase 2: Future Extensions (out of scope)

- Add `asset` table for vector/metadata storage
- Add `sidecar_ref` table for auxiliary files
- Add RLS policies for org_id scoping (Supabase prod)
- Add partitioning for job_event (by ts) for scalability

---

## Naming Conventions

All database objects follow these conventions to ensure Alembic autogenerate stability:

- **Tables**: Singular nouns (e.g., `job`, not `jobs`)
- **Columns**: snake_case
- **Primary Keys**: `pk_{table_name}`
- **Foreign Keys**: `fk_{table_name}_{ref_table}_{column}`
- **Indexes**: `idx_{table_name}_{column(s)}`
- **Unique Constraints**: `uq_{table_name}_{column(s)}`
- **Check Constraints**: `ck_{table_name}_{description}`

---

## Local vs. Supabase

| Aspect | Local Dev | Supabase Prod |
|--------|-----------|---------------|
| Migration Engine | Alembic Python | Compiled SQL artifacts |
| Migration Location | `packages/common/alembic/` | `supabase/migrations/` |
| Execution | `alembic upgrade head` | Supabase CLI / Dashboard |
| RLS Policies | Not applied | Applied via Supabase SQL |
| Auth Integration | None | Supabase Auth |

**Note**: Alembic generates the source-of-truth migrations. Supabase SQL artifacts are compiled outputs (`alembic upgrade head --sql`) committed to the repo for production deployment.

---

## References

- Alembic env: `packages/common/alembic/env.py`
- SQLAlchemy models: `packages/common/src/heimdex_common/models.py`
- Configuration: `../development/configuration.md`
- Architecture: `../architecture/overview.md`
