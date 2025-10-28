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
  api/        # FastAPI service scaffolding with /healthz
  worker/     # Background worker heartbeat process
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
2. Copy `deploy/.env.example` to `deploy/.env` and adjust credentials for your local stack.
3. Install [pre-commit](https://pre-commit.com) and run `pre-commit install` to enable linting hooks.
4. Use `make up` to build and start the services (API, worker, Postgres, Redis).
5. Verify the API health endpoint with `make health`.

## Testing the Pipeline

The async job infrastructure is now operational. Test it with these commands:

```bash
# Submit a job
make test-job

# Check job status (run multiple times to watch progress)
make check-job

# Test failure and retry behavior
make test-job-fail
make check-job  # Wait ~10 seconds, check again to see retries
```

Jobs progress through three mock stages simulating video processing:
- **extracting** (2s): Frame extraction
- **analyzing** (3s): Scene detection
- **indexing** (1s): Vector generation

See `docs/api.md` for detailed API documentation.

## Development Commands

```bash
make up          # Start all services
make down        # Stop all services
make logs        # Tail service logs
make health      # Check API health
make reset       # Reset database and Redis (down -v, then up)
make test-job    # Submit a test job
make check-job   # Check last job status
```

Future steps will add real video processing (FFmpeg, scene detection, embeddings) and cloud storage integration.
