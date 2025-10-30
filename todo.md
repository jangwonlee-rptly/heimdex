# Heimdex TODO Tracker

This file serves as an authoritative list of outstanding placeholders, mock implementations, and follow-up tasks that have been identified across the repository. It is intended to be a living document, updated as new tasks are discovered and completed.

| Area | File / Location | Details | Suggested Next Step |
| --- | --- | --- | --- |
| **Architecture** | | | |
| Sidecar Schema Definition | `docs/architecture/sidecar-schema.md` | The document for the sidecar metadata file is currently a placeholder. A concrete schema is required for workers to produce and for the API to consume this metadata. | Define the full JSON schema for the sidecar files, including fields for scenes, transcripts, captions, faces, and embeddings. Provide clear type definitions and example values. |
| **Worker Implementation** | | | |
| Mock Job Processing | `apps/worker/src/heimdex_worker/tasks.py` | The `process_mock` actor is a placeholder that simulates a multi-stage pipeline with `time.sleep`. This needs to be replaced with actual media processing logic. | Implement the real video processing pipeline, likely involving multiple actors for different stages (e.g., frame extraction with FFmpeg, transcription with an ASR model, embedding generation). |
| **Configuration & Deployment** | | | |
| Production Configuration | `README.md`, `deploy/.env.example` | The documentation and example environment files note that the default credentials are for local development only and must be changed for production. | Establish a secure process for managing production secrets (e.g., using a cloud provider's secret manager) and update deployment guides accordingly. |
| Terraform Placeholders | `infra/terraform/main.tf` | The Terraform configuration for Cloud Run contains placeholder environment variables that are intended to be overridden. | Integrate the Terraform setup with a secrets management solution to inject production-ready credentials for Postgres, Redis, etc., during deployment. |
| Placeholder Container Images | `docs/infrastructure/deployment.md` | The deployment documentation notes that the Terraform scripts currently reference placeholder container images. | Set up a CI/CD pipeline that builds and pushes versioned Docker images to a container registry (e.g., Artifact Registry, Docker Hub). Update Terraform to use these images. |
| **Developer Experience** | | | |
| Makefile Targets | `Makefile` | Several `make` targets, such as `lint`, `fmt`, and `setup`, are currently placeholders that only print a message. | Implement the logic for these Makefile targets to run the appropriate development commands (e.g., `ruff check .`, `black .`, `uv pip install -r requirements.txt`). |
