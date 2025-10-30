# Alembic Migration Playbook (Containerized)

This guide documents how to manage Heimdex database migrations **inside the API container as `appuser`**. All commands run against the Docker Compose stack (`deploy/docker-compose.yml`) and rely on the code copied into the image (`/app`).

## Prerequisites
- Docker Compose stack is up (`docker compose -f deploy/docker-compose.yml up -d --build`).
- PostgreSQL service (`pg`) is healthy; the Compose file exposes service DNS names (`pg`, `redis`, …).
- The API image already contains the latest source (run with `--build` after code changes).

## 1. Autogenerate a Revision
```bash
docker compose -f deploy/docker-compose.yml exec -u appuser api bash -lc '\
  cd /app/packages/common && \
  ALEMBIC_CONFIG=/app/packages/common/alembic.ini \
  PYTHONPATH=/app/packages/common/src \
  python -m alembic revision --autogenerate -m "hardening: job ledger enums/indexes/idempotency"'
```
- Output appears in `/app/packages/common/alembic/versions`. Copy curated revision back to the host (e.g. `docker compose ... cp`).

## 2. Upgrade the Dev Database
```bash
docker compose -f deploy/docker-compose.yml exec -u appuser api bash -lc '\
  cd /app/packages/common && \
  ALEMBIC_CONFIG=/app/packages/common/alembic.ini \
  PYTHONPATH=/app/packages/common/src \
  python -m alembic upgrade head'
```
- Repeat with `alembic downgrade 001_job_ledger_init` followed by `alembic upgrade head` to validate upgrade paths from the previous revision.

## 3. Compile Supabase SQL Artifact
1. Generate SQL inside the container (write to a writable path such as `/tmp`):
   ```bash
   docker compose -f deploy/docker-compose.yml exec -u appuser api bash -lc '\
     cd /app/packages/common && \
     ALEMBIC_CONFIG=/app/packages/common/alembic.ini \
     PYTHONPATH=/app/packages/common/src \
     python -m alembic upgrade 001_job_ledger_init:3af4686817cc --sql \
     > /tmp/0002_job_ledger_hardening.sql'
   ```
2. Copy the artifact to the repo:
   `docker compose -f deploy/docker-compose.yml cp api:/tmp/0002_job_ledger_hardening.sql supabase/migrations/0002_job_ledger_hardening.sql`

## Common Issues & Fixes
| Symptom | Cause | Remedy |
|---------|-------|--------|
| `ModuleNotFoundError` during autogenerate | `PYTHONPATH` missing project sources | Prefix commands with `PYTHONPATH=/app/packages/common/src[:...]` |
| `Permission denied` writing under `/app` | `appuser` lacks directory | Write to `/tmp` and `docker compose cp` back to the host; add directories at build time if needed |
| `column ... cannot be cast automatically` | Enum migration missing `USING` clause or status normalization | Update migration to run `UPDATE` statements and supply `postgresql_using` |
| `No such file or directory` for compiled SQL path | `supabase/migrations` not present in image | Use `/tmp` as scratch space, then copy to host repo |

## Cleanup
```bash
docker compose -f deploy/docker-compose.yml down -v
```

Keep this playbook with migration PRs to document the exact commands executed and any manual edits made to the revision.
