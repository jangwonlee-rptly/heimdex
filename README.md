# Heimdex: A Vector-Native Media Archival Platform

Heimdex is a powerful, vector-native archival platform designed to make massive video libraries searchable without forcing re-uploads or manual tagging. It connects directly to your existing storage (starting with Google Drive), ingests video assets, extracts rich, structured metadata, and exposes a hybrid semantic search API.

## Core Problem & Solution

Production houses, creative agencies, and media companies often have petabytes of video assets scattered across various storage systems. Finding a specific clip—"the shot of a sunset over the mountains from the Q2 campaign"—is a manual, time-consuming, and often impossible task.

Heimdex solves this by:

1. **Connecting, Not Copying**: It indexes your media where it lives, creating a unified search layer without data duplication.
2. **Automated Deep Metadata Extraction**: It runs AI pipelines (ffmpeg, ASR, vision captioning, face detection) to generate rich, time-coded metadata.
3. **Hybrid Search**: It combines traditional keyword search with modern vector-based semantic search, allowing you to find content based on concepts and context, not just tags.

---

## Key Features

- **Unified Access**: Bring distributed production archives into a single, searchable index while assets stay in place.
- **Rich Metadata Sidecars**: Generate detailed JSON sidecars containing scenes, transcripts, captions, faces, and other derived signals for every asset.
- **Secure by Design**: Built with Supabase for robust authentication with row-level security, private object storage (MinIO/S3), and private vector search (Qdrant).
- **Composable & Cloud-Agnostic**: A modern architecture using FastAPI, async workers (Dramatiq), and declarative infrastructure (Docker Compose, Make) for reproducible, cloud-agnostic deployments.

---

## System Architecture

Heimdex follows a modular, microservices-oriented architecture designed for scalability and maintainability.

### High-Level Flow

```
Client → FastAPI API → Redis/Dramatiq Queue → Worker →
  ├─ AI/ML Pipelines (ffmpeg, vision, etc.) → Sidecar JSON → MinIO/S3
  └─ Structured Metadata → Postgres → Qdrant Vectors
```

1. **API Layer**: A FastAPI service handles ingestion requests, search queries, and user management. It validates requests, creates job records in Postgres, and enqueues tasks in Redis.
2. **Job Queue**: Redis, managed by the Dramatiq library, acts as a robust message broker, decoupling the API from the background workers.
3. **Worker Layer**: A pool of asynchronous workers consumes tasks from the queue. They perform the heavy lifting of running AI pipelines to extract metadata.
4. **Data Persistence**:
    - **Postgres (via Supabase)**: Stores structured metadata, user information, and job states with per-tenant row-level security.
    - **Qdrant**: A dedicated vector database that stores text and image embeddings for semantic search.
    - **MinIO/S3**: An object store for the generated metadata sidecar files and thumbnails.

---

## Repository Layout

```
apps/
  api/        # FastAPI service: handles HTTP requests, enqueues jobs.
  worker/     # Background worker: executes long-running tasks.
packages/
  common/     # Shared Python code: models, db connections, config.
deploy/       # Deployment assets: Docker Compose, .env files, Makefile.
  docker-compose.yml
  .env.example
docs/
  architecture.md
  sidecar-schema.md
infra/        # (Future) Terraform or IaC for cloud deployments.
```

---

## Getting Started: Local Development

Follow these steps to get the complete Heimdex platform running on your local machine.

### Prerequisites

- [Docker](https://www.docker.com/get-started) and Docker Compose
- [Python](https://www.python.org/downloads/) (3.11+)
- [pre-commit](https://pre-commit.com) for code quality hooks

### 1. Clone the Repository

```bash
git clone https://github.com/your-org/heimdex.git
cd heimdex
```

### 2. Set Up Environment Configuration

The entire platform is configured via environment variables, managed by a `.env` file for local development.

- Copy the example environment file:

    ```bash
    cp deploy/.env.example deploy/.env
    ```

- **No changes are needed to `.env` for the default local setup.** The provided credentials are for the local Docker-based services. For a production environment, you would replace these with your actual database, Redis, and Supabase credentials.

### 3. Install Pre-commit Hooks

We use `pre-commit` to automatically run linters (Ruff, Black) and type checkers (MyPy) before each commit. This ensures code quality and consistency.

```bash
pre-commit install
```

### 4. Start All Services

The `Makefile` provides a convenient wrapper around Docker Compose to manage the application stack.

```bash
make up
```

This single command will:

- Build the Docker images for the `api` and `worker` services.
- Start all containers: `api`, `worker`, `postgres`, `redis`, `qdrant`, and `minio`.
- Mount the local source code into the containers, enabling hot-reloading for the API service.

### 5. Verify the Setup

Check that the API service is running and healthy by using the health check command:

```bash
make health
```

You should see a JSON response with `"ok": true`. You can now access the interactive API documentation at [http://localhost:8000/docs](http://localhost:8000/docs).

---

## Testing the Job Processing Pipeline

The asynchronous job pipeline is the core of Heimdex. You can test its functionality with the following `make` commands.

### Mock Processing Stages

For development, jobs progress through three mock stages that simulate a real video processing pipeline, with built-in delays:

- **extracting** (2s): Simulates frame extraction.
- **analyzing** (3s): Simulates scene detection and analysis.
- **indexing** (1s): Simulates vector generation and indexing.

**Note**: In a production environment, these mock stages would be replaced with actual video processing logic.

### 1. Submit a Successful Job

This command sends a request to the API to create a new job that is expected to succeed.

```bash
make test-job
```

### 2. Check the Job's Status

Run this command multiple times to see the job's `status` and `stage` progress from `pending` to `processing` and finally to `completed`.

```bash
make check-job
```

### 3. Test Failure and Retries

This command submits a job that is programmed to fail at the "analyzing" stage.

```bash
make test-job-fail
```

Check the status (`make check-job`). You will see it move to `failed`. Because the worker is configured with a retry policy, Dramatiq will automatically re-queue the job. After a short backoff period, check the status again, and you will see it being processed a second time.

---

## Core Development Philosophy

- **Vector-Native First**: We believe vector search is the future of data retrieval for unstructured data. Our architecture prioritizes it as a foundational component.
- **Extensible and Modular**: The platform is a collection of modular services. This allows for independent scaling, development, and the flexibility to swap out components (e.g., AI models, storage backends) as technology evolves.
- **Infrastructure as Code (IaC)**: All infrastructure is defined declaratively using Docker Compose and Makefiles, ensuring development, testing, and production environments are consistent and reproducible.
- **Developer Experience Focused**: We strive for a seamless developer experience through comprehensive documentation, a robust testing framework, and automated quality checks with `pre-commit`.

---

## Development Commands

```bash
make up          # Start all services with Docker Compose.
make down        # Stop all services.
make logs        # Tail the logs of all running services.
make health      # Check the API health endpoint (/healthz).
make reset       # Reset the entire stack (stops, removes volumes, and starts again).
make test-job    # Submit a successful test job.
make check-job   # Check the status of the last submitted job.
make test-job-fail # Submit a failing test job.
```

For detailed API documentation, please see `docs/api.md`.
