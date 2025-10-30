# Heimdex TODO Tracker

Authoritative list of outstanding placeholders, mock implementations, and follow-up tasks discovered across the repository.

| Area | File / Location | Details | Suggested Next Step |
| --- | --- | --- | --- |
| Sidecar schema contract | `architecture/sidecar-schema.md` (line 3) | Document still contains a `TODO` requesting the JSON schema for scenes, transcripts, captions, faces. | Draft the sidecar JSON schema (fields, types, sample) or link to its canonical source once defined. |
| Developer Makefile tasks | `Makefile` (lines 4-10) | `lint`, `fmt`, and `setup` targets only emit “placeholder” messages. | Wire these targets to real commands (e.g., `ruff`, `black`, `uv sync`) or remove if redundant. |
| Mock job pipeline | `apps/worker/src/heimdex_worker/tasks.py` (process_mock docstring) | Worker actor explicitly marked as a placeholder for real video processing. | Replace with actual ingest/processing pipeline (FFmpeg, ASR, embeddings) or split into separate top-level actor once implementation is ready. |
| Production readiness of mock stages | `README.md` (Mock Processing Stages section) | Documentation states the current mock stages must be replaced before production rollout. | Plan and implement the real media processing workflow; update README once complete. |
| Cloud Run placeholder configuration | `infra/terraform/main.tf` (around lines 136-216) | Cloud Run definitions include placeholder env vars (`PGHOST`, `REDIS_URL`) intended for override via Secret Manager. | Replace with environment-specific variables or Secret Manager references prior to production deploys. |
| Placeholder container images | `docs/infrastructure/deployment.md` (Created Resources list) | Deployment guide notes that Cloud Run services currently use placeholder images. | Update Terraform + documentation to pull built artifacts (e.g., Artifact Registry images produced by CI). |
