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

Heimdex is built on a set of core principles that guide our technical decisions and long-term vision:

-   **Vector-Native First**: We believe that vector search is the future of data retrieval for unstructured and semi-structured data. Our architecture prioritizes a vector-native approach, ensuring that embeddings and semantic search are foundational, not an afterthought.

-   **Extensible and Modular**: The platform is designed as a collection of modular services that communicate through well-defined APIs and message queues. This allows for independent scaling, development, and the flexibility to swap out components (e.g., different AI models, storage backends) as technology evolves.

-   **Infrastructure as Code (IaC)**: All infrastructure is defined declaratively using tools like Docker Compose and Makefiles. This ensures that development, testing, and production environments are consistent, reproducible, and easy to manage.

-   **Developer Experience Focused**: We strive to create a seamless and productive developer experience. This is achieved through comprehensive documentation, a robust testing framework, and automated quality checks with pre-commit hooks (Ruff, Black, MyPy).

-   **Cloud-Agnostic and Open Source**: Heimdex is built with open-source components (FastAPI, Qdrant, Postgres) and is designed to be cloud-agnostic. This avoids vendor lock-in and provides the flexibility to deploy on any cloud provider or on-premises infrastructure.

## Getting Started

To get the Heimdex platform running locally for development, follow these steps:

1.  **Clone the Repository**:
    ```bash
    git clone https://github.com/your-org/heimdex.git
    cd heimdex
    ```

2.  **Set Up Environment**:
    - Create a Python virtual environment using your preferred tool (e.g., `venv`, `conda`).
    - Copy the example environment file and customize it for your local setup:
      ```bash
      cp deploy/.env.example deploy/.env
      ```
    - **Note**: The default credentials in `.env.example` are suitable for local development but should be changed for a production environment.

3.  **Install Pre-commit Hooks**:
    - Install [pre-commit](https://pre-commit.com) to ensure code quality and consistency.
    - Run the following command to set up the Git hooks:
      ```bash
      pre-commit install
      ```

4.  **Start the Services**:
    - Use the provided Makefile to build and launch all services with Docker Compose:
      ```bash
      make up
      ```
    - This command will start the API, worker, Postgres database, and Redis broker.

5.  **Verify the Setup**:
    - Check that the API is running correctly by hitting the health endpoint:
      ```bash
      make health
      ```

## Testing the Pipeline

The asynchronous job processing pipeline is fully operational. You can test its functionality with the following commands:

-   **Submit a Job**:
    ```bash
    make test-job
    ```

-   **Check Job Status**:
    - Run this command multiple times to observe the job's progress.
    ```bash
    make check-job
    ```

-   **Test Failure and Retries**:
    - This command simulates a failure at the "analyzing" stage.
    ```bash
    make test-job-fail
    ```
    - Check the job's status again after a few seconds to see the retry mechanism in action.
    ```bash
    make check-job
    ```

### Mock Processing Stages

For development and testing, jobs progress through three mock stages that simulate a real video processing pipeline:
-   **extracting** (2s): Simulates frame extraction.
-   **analyzing** (3s): Simulates scene detection and analysis.
-   **indexing** (1s): Simulates vector generation and indexing.

**Note for Production**: These mock stages should be replaced with actual video processing logic (e.g., using FFmpeg, computer vision models) before deploying to a production environment.

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
