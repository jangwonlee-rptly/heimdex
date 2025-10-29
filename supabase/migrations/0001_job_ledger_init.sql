-- Initial job ledger schema with job and job_event tables
-- Compiled from Alembic migration: 001_job_ledger_init
-- Date: 2025-10-28
--
-- This migration establishes the canonical durable job ledger with:
-- - job table: operational state for async jobs (replaces old jobs table)
-- - job_event table: immutable audit log for state transitions
--
-- The schema supports:
-- - Multi-tenancy via org_id (for future RLS in Supabase)
-- - Idempotent job creation via idempotency_key
-- - Retry logic with attempt counter
-- - State machine: queued → running → (succeeded|failed|canceled|dead_letter)
-- - Full audit trail of all state transitions

-- Drop old jobs table if it exists (superseded by new schema)
DROP TABLE IF EXISTS jobs CASCADE;

-- Create job table
CREATE TABLE job (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    type VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'queued',
    attempt INTEGER NOT NULL DEFAULT 0,
    priority INTEGER NOT NULL DEFAULT 0,
    idempotency_key VARCHAR(255),
    requested_by VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    last_error_code VARCHAR(100),
    last_error_message TEXT,

    -- Constraints
    CONSTRAINT ck_job_status CHECK (
        status IN ('queued', 'running', 'succeeded', 'failed', 'canceled', 'dead_letter')
    ),
    CONSTRAINT uq_job_org_idempotency UNIQUE (org_id, idempotency_key)
        WHERE idempotency_key IS NOT NULL
);

-- Comment on table
COMMENT ON TABLE job IS 'Durable ledger for asynchronous jobs with retry and idempotency support';

-- Comments on columns
COMMENT ON COLUMN job.id IS 'Globally unique job identifier';
COMMENT ON COLUMN job.org_id IS 'Organization/tenant identifier for RLS';
COMMENT ON COLUMN job.type IS 'Job type discriminator (e.g., ''mock_process'', ''drive_ingest'')';
COMMENT ON COLUMN job.status IS 'Current job state';
COMMENT ON COLUMN job.attempt IS 'Retry attempt counter (0 = first attempt)';
COMMENT ON COLUMN job.priority IS 'Job priority (higher = more urgent, future use)';
COMMENT ON COLUMN job.idempotency_key IS 'Client-provided key for deduplication';
COMMENT ON COLUMN job.requested_by IS 'User/service that requested the job';
COMMENT ON COLUMN job.created_at IS 'Job creation timestamp';
COMMENT ON COLUMN job.updated_at IS 'Last modification timestamp';
COMMENT ON COLUMN job.started_at IS 'When job execution started';
COMMENT ON COLUMN job.finished_at IS 'When job reached terminal state';
COMMENT ON COLUMN job.last_error_code IS 'Error classification (e.g., ''TIMEOUT'', ''VALIDATION_ERROR'')';
COMMENT ON COLUMN job.last_error_message IS 'Human-readable error detail';

-- Create indexes for job table
CREATE INDEX idx_job_org_status ON job (org_id, status, created_at);
CREATE INDEX idx_job_type_status ON job (type, status);

-- Create job_event table
CREATE TABLE job_event (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES job(id) ON DELETE CASCADE,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    prev_status VARCHAR(50),
    next_status VARCHAR(50) NOT NULL,
    detail_json JSONB
);

-- Comment on table
COMMENT ON TABLE job_event IS 'Immutable audit log of job state transitions';

-- Comments on columns
COMMENT ON COLUMN job_event.id IS 'Unique event identifier';
COMMENT ON COLUMN job_event.job_id IS 'Reference to parent job';
COMMENT ON COLUMN job_event.ts IS 'Event occurrence timestamp';
COMMENT ON COLUMN job_event.prev_status IS 'Status before transition (NULL for initial state)';
COMMENT ON COLUMN job_event.next_status IS 'Status after transition';
COMMENT ON COLUMN job_event.detail_json IS 'Additional event metadata (stage, progress, error details)';

-- Create indexes for job_event table
CREATE INDEX idx_job_event_job_ts ON job_event (job_id, ts);
CREATE INDEX idx_job_event_ts ON job_event (ts);
