# Heimdex Documentation Index

Curated entry point for the Heimdex knowledge base. Documents are grouped by topic and mirror the current FastAPI + Dramatiq architecture, infrastructure tooling, and migration workflow.

## Architecture

- `architecture/overview.md` — System-level design, data flow, and readiness probes.
- `architecture/sidecar-schema.md` — Placeholder for the sidecar JSON contract (needs population).

## API

- `api/overview.md` — FastAPI routes for job creation and status polling.

## Development

- `development/configuration.md` — Environment variables and shared configuration model (Pydantic settings).

## Infrastructure

- `infrastructure/deployment.md` — Terraform- and Docker-based deployment guide for GCP (Cloud Run, Artifact Registry, WIF).

## Security

- `security/overview.md` — Platform security posture, network boundaries, and hardening guidance.
- `security/auth.md` — Supabase-auth integration patterns and local dev authentication fallbacks.

## Migration & Persistence

- `migration/2025-10-28-migration-to-alembic.md` — Change log for the Alembic introduction and schema hardening.
- `migration/db-schema.md` — Canonical Postgres schema reference (job / job_event ledger).
- `migration/migration-report.md` — SQLAlchemy ORM adoption report (psycopg2 → SQLAlchemy 2.0).
- `migration/migration-inventory.md` — Inventory of migration tasks, open risks, and validation steps.
- `migration/sqlalchemy-developer-guide.md` — ORM usage patterns, repository layer, and testing guidance.
- `migration/testing-migrations.md` — Container-native Alembic runbook (autogenerate, upgrade, compile SQL).
