# Documentation Maintenance Report — 2025-10-29

## Reorganization Summary

| New Path | Previous Location |
| --- | --- |
| architecture/overview.md | architecture.md |
| architecture/sidecar-schema.md | sidecar-schema.md |
| api/overview.md | api.md |
| development/configuration.md | configuration.md |
| infrastructure/deployment.md | deploy.md |
| security/overview.md | security.md |
| security/auth.md | auth.md |
| migration/2025-10-28-migration-to-alembic.md | 2025-10-28-migration-to-alembic.md |
| migration/db-schema.md | db-schema.md |
| migration/migration-report.md | MIGRATION_REPORT.md |
| migration/migration-inventory.md | migration_inventory.md |
| migration/sqlalchemy-developer-guide.md | SQLALCHEMY_DEVELOPER_GUIDE.md |
| migration/testing-migrations.md | TESTING_MIGRATIONS.md |

No documents required deprecation or archival in this pass.

## Missing or Thin Coverage

| Area | Gap | Suggested Action |
| --- | --- | --- |
| Worker pipeline details | `apps/worker/src/heimdex_worker/tasks.py` simulates multi-stage jobs, but there is no companion doc explaining stage semantics, retry behaviour, or eventual real pipeline requirements. | Add `development/worker-pipeline.md` covering task design, stage transitions, and hooks for real ingestion. |
| Readiness probe profiles | Recent enhancements in `packages/common/src/heimdex_common/probes.py` (profile-aware caching/backoff) are only mentioned indirectly in architecture docs. | Extend `architecture/overview.md` or add `operations/readiness.md` to describe probe toggles, caching, and configuration flags. |
| Sidecar schema contract | `architecture/sidecar-schema.md` remains a TODO placeholder. | Define the JSON schema structure (frames, transcripts, embeddings) or replace with a link to the eventual schema source. |
| IaC specifics | Terraform modules, Secret Manager usage, and Cloud Run provisioning are high-level in `infrastructure/deployment.md`; there is no breakdown of module layout or variables. | Add `infrastructure/terraform.md` describing module structure, remote state, and environment promotion workflow. |
| Supabase multi-tenancy rollout | Security/auth documentation outlines current Supabase flow but lacks guidance on row-level security and tenant scoping (referenced by code via `org_id`). | Add a future `security/multi-tenancy.md` once Supabase RLS policies are finalized. |

## Suggested Follow-Ups

1. Draft `development/worker-pipeline.md` documenting current job stages, failure injection flags, and the roadmap toward real media processing.
2. Flesh out `architecture/sidecar-schema.md` with an initial JSON schema or link to canonical source-of-truth (e.g., OpenAPI/JSON Schema).
3. Create `infrastructure/terraform.md` summarizing modules, backend configuration, and deployment commands.
4. Produce `security/multi-tenancy.md` once Supabase RLS and auth integration stabilise.
5. Consider an `operations/readiness.md` addendum detailing probe toggles (ENABLE_PG_PROBE, etc.) and cached interval semantics.
