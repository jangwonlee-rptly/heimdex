# Heimdex

Heimdex is a vector-native archival platform built to make massive video libraries searchable without forcing re-uploads or manual tagging. It connects directly to customer-managed storage (starting with Google Drive shared folders), ingests video assets, extracts structured metadata, and exposes hybrid semantic search over rich sidecar data.

## Why Heimdex
- **Unified access**: Bring distributed production archives into a single searchable index while assets stay in place.
- **Rich metadata**: Generate sidecar JSONs containing scenes, transcripts, captions, faces, and other derived signals.
- **Secure by design**: Supabase authentication with row-level security, private object storage (MinIO/S3), and private vector search (Qdrant).
- **Composable architecture**: FastAPI services, async workers, and declarative infrastructure for reproducible deployments.

## Repository Layout
```
apps/
  api/        # FastAPI application (placeholder)
  worker/     # Background job runner (placeholder)
packages/
  common/     # Shared models, helpers, and configuration
deploy/
  docker-compose.yml
  .env.example
  Makefile
docs/
  architecture.md
  sidecar-schema.md
```

## Long-Term Architecture
1. **API layer**: FastAPI service handles ingestion requests, search queries, and orchestration.
2. **Job execution**: Redis/Dramatiq-backed worker runs ffmpeg, ASR, vision captioning, and face detection pipelines.
3. **Metadata persistence**: Postgres (via Supabase) stores structured metadata with per-tenant row-level security.
4. **Vector indexing**: Qdrant holds hybrid text/vector embeddings from transcripts and visual descriptors.
5. **Asset storage**: MinIO/S3 stores generated sidecars and thumbnails alongside customer-managed originals.

```
Client → FastAPI API → Redis/Dramatiq queue → Worker →
  ├─ ffmpeg + AI pipelines → Sidecar JSON → MinIO/S3
  └─ Structured metadata → Postgres → Qdrant vectors
```

## Development Philosophy
- **Infrastructure as code**: Docker Compose, Makefiles, and CI/CD workflows ensure reproducible environments.
- **Lint-first**: Ruff, Black, and MyPy run via pre-commit to keep the codebase healthy from the start.
- **Modular services**: Clear separation between API, worker, and shared packages keeps the mono-repo maintainable.

## Getting Started
1. Clone the repository and create a Python virtual environment of your choice.
2. Copy `deploy/.env.example` to `.env` and adjust credentials for your local stack.
3. Install [pre-commit](https://pre-commit.com) and run `pre-commit install` to enable linting hooks.
4. Use `make up` and `make down` (placeholders for now) to manage infrastructure as it evolves.

Future steps will introduce service implementations, Docker images, and integration plumbing. For now, this repository provides a clean scaffold to build on.
