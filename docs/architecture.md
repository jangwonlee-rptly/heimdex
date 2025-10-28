# Heimdex Architecture Overview

Heimdex orchestrates a pipeline that ingests customer-owned video libraries, extracts structured intelligence, and exposes tenant-scoped semantic search without moving the original assets. The platform relies on Supabase for authentication and access control, a FastAPI service for coordination, a Redis/Dramatiq worker tier for heavy processing, and specialized stores (Postgres, Qdrant, MinIO/S3) to retain derived insights.

```
Customer Drive → Ingestion Trigger → FastAPI API → Redis/Dramatiq queue → Worker
      ↓                                         ↓                        ↓
 Original video (unaltered)     Structured metadata → Postgres         Vector embeddings → Qdrant
                                                                  Sidecar JSON + media → MinIO/S3
```
