# Heimdex Architecture Overview

Heimdex orchestrates a pipeline that ingests customer-owned video libraries, extracts structured intelligence, and exposes tenant-scoped semantic search without moving the original assets. The platform relies on Supabase for authentication and access control, a FastAPI service for coordination, a Redis/Dramatiq worker tier for heavy processing, and specialized stores (Postgres, Qdrant, MinIO/S3) to retain derived insights.

```
Customer Drive → Ingestion Trigger → FastAPI API → Redis/Dramatiq queue → Worker
      ↓                                         ↓                        ↓
 Original video (unaltered)     Structured metadata → Postgres         Vector embeddings → Qdrant
                                                                  Sidecar JSON + media → MinIO/S3
```

## Health & Operations

- API service exposes `/healthz` returning static metadata (service, version, environment, boot timestamp) to satisfy orchestration health probes without leaking infrastructure details.
- Worker service runs a long-lived heartbeat loop that emits JSON logs every ~20 seconds and acknowledges SIGTERM before exiting with status `0`.
- Both services log exclusively in single-line JSON with `ts`, `service`, `env`, `version`, `level`, and `msg` to keep observability tooling uniform.
- Docker healthchecks monitor HTTP readiness for the API and process liveness for the worker, enabling future dependencies (Postgres, Qdrant, MinIO) to chain start-up on healthy signals.
