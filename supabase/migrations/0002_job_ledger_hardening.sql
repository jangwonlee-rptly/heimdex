BEGIN;

-- Running upgrade 001_job_ledger_init -> 3af4686817cc

CREATE TYPE job_status AS ENUM ('queued', 'running', 'succeeded', 'failed', 'canceled', 'dead_letter');

CREATE TYPE job_backoff_policy AS ENUM ('none', 'fixed', 'exp');

UPDATE job SET status = 'queued' WHERE status IN ('pending', 'queued');

UPDATE job SET status = 'running' WHERE status IN ('processing', 'running');

UPDATE job SET status = 'succeeded' WHERE status IN ('completed', 'succeeded');

ALTER TABLE job ADD COLUMN max_attempts INTEGER DEFAULT 5 NOT NULL;

COMMENT ON COLUMN job.max_attempts IS 'Maximum retry attempts before dead-lettering';

ALTER TABLE job ADD COLUMN backoff_policy job_backoff_policy DEFAULT 'exp'::job_backoff_policy NOT NULL;

COMMENT ON COLUMN job.backoff_policy IS 'Backoff policy for retry scheduling';

ALTER TABLE job ALTER COLUMN status DROP DEFAULT;

ALTER TABLE job ALTER COLUMN status TYPE job_status USING status::job_status;

ALTER TABLE job ALTER COLUMN status SET DEFAULT 'queued'::job_status;

ALTER TABLE job ALTER COLUMN last_error_code TYPE VARCHAR(64);

ALTER TABLE job ALTER COLUMN last_error_message TYPE VARCHAR(2048);

DROP INDEX idx_job_org_status;

DROP INDEX idx_job_type_status;

DROP INDEX uq_job_org_idempotency;

CREATE INDEX idx_job__job_org_id ON job (org_id);

CREATE INDEX idx_job__org_id_created_at_desc ON job (org_id, created_at DESC);

CREATE UNIQUE INDEX idx_job__org_id_idempotency_key ON job (org_id, idempotency_key) WHERE idempotency_key IS NOT NULL;

CREATE INDEX idx_job__status_created_at ON job (status, created_at);

ALTER TABLE job ADD CONSTRAINT ck_job__status_finished_at_consistency CHECK ((status IN ('succeeded', 'failed', 'canceled', 'dead_letter') AND finished_at IS NOT NULL) OR (status IN ('queued', 'running') AND finished_at IS NULL));

DROP INDEX idx_job_event_job_ts;

DROP INDEX idx_job_event_ts;

CREATE INDEX idx_job_event__job_id_ts ON job_event (job_id, ts);

CREATE INDEX idx_job_event__ts ON job_event (ts);

UPDATE alembic_version SET version_num='3af4686817cc' WHERE alembic_version.version_num = '001_job_ledger_init';

COMMIT;
