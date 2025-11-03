# Heimdex Pre-Business-Logic Readiness Checklist (v1)

This document enumerates every task, technical TODO, and structural improvement that should be completed before writing any new business logic in the Heimdex codebase. Its goal is to ensure the entire system is rock solid, consistent, and maintainable before business features are added.

---

## 1. :jigsaw: Codebase Hygiene

| Category | File / Path | Short Description | Why it Matters | Priority |
|---|---|---|---|---|
| Refactoring | `apps/api/src/heimdex_api/vectors.py` | The `query_model_ver` is hardcoded to `v1`. | Hardcoded values make the code less flexible and harder to maintain. | P2 |
| Dependency Management | `pyproject.toml` | Dependency versions are not pinned. | Unpinned dependencies can lead to unexpected build failures and bugs. | P1 |
| Configuration | `deploy/.env.example` | The `.env.example` file contains default credentials. | Default credentials are a security risk and should not be used in production. | P0 |
| Code Removal | `docs/qdrant-mock-to-production.md` | The documentation refers to a deprecated `/vectors/mock` endpoint. | Deprecated code and documentation can confuse new developers. | P3 |

---

## 2. :gear: Infrastructure & Deployment

| Category | File / Path | Short Description | Why it Matters | Priority |
|---|---|---|---|---|
| Terraform | `infra/terraform/main.tf` | The `main.tf` file contains placeholder values for `PGHOST` and `REDIS_URL`. | Placeholders need to be replaced with actual production values. | P0 |
| Secrets Management | `infra/terraform/main.tf` | The `dev_jwt_secret` is managed in Terraform. | A more robust solution for production would be to use a dedicated secrets management tool. | P1 |
| Resource Limits | `infra/terraform/main.tf` | The Cloud Run resource limits should be reviewed and adjusted. | Incorrect resource limits can lead to performance issues and unnecessary costs. | P1 |
| Autoscaling | `infra/terraform/main.tf` | A more comprehensive autoscaling strategy should be developed. | Autoscaling is essential for handling variable loads and ensuring high availability. | P1 |
| Local vs. Production Parity | `deploy/.env.example`, `infra/terraform/main.tf` | The `AUTH_PROVIDER` is hardcoded to `dev`. | This should be parameterized to allow for different authentication providers in different environments. | P0 |
| Redis Persistence | `deploy/docker-compose.yml` | A more robust persistence and backup strategy should be implemented for Redis. | The current configuration is not suitable for production. | P1 |
| Database Migrations | `Makefile` | There's no automated process for running migrations as part of the deployment pipeline. | Automated migrations are essential for ensuring that the database schema is always up-to-date. | P1 |

---

## 3. :test_tube: Testing & Quality Gates

| Category | File / Path | Short Description | Why it Matters | Priority |
|---|---|---|---|---|
| Unit Tests | `apps/api`, `apps/worker` | There are no unit tests for the `api` and `worker` applications. | Unit tests are essential for ensuring the quality of the code and preventing regressions. | P1 |
| Integration Tests | `packages/common/tests` | There are no integration tests for the job processing pipeline or the outbox dispatcher. | Integration tests are essential for ensuring that the different parts of the system work together correctly. | P1 |
| Test Naming Convention | `.pre-commit-config.yaml` | The pre-commit hooks do not enforce a consistent test naming convention. | A consistent naming convention makes it easier to find and run tests. | P3 |
| Docstring Coverage | `.pre-commit-config.yaml` | The pre-commit hooks do not check for docstring coverage. | Docstrings are essential for understanding the code and for generating documentation. | P2 |
| Flaky Tests | `Makefile` | The `test-integration` target in the `Makefile` has `|| true` at the end. | This can hide flaky tests and should be removed. | P1 |
| CI Triggers | `.github/workflows/ci.yml` | The CI pipeline is not triggered on changes to the `infra` directory. | This could lead to a situation where the infrastructure and the application are out of sync. | P2 |

---

## 4. :brain: Observability & Monitoring

| Category | File / Path | Short Description | Why it Matters | Priority |
|---|---|---|---|---|
| Metrics | N/A | There is no implementation for collecting and exposing metrics. | Metrics are essential for understanding the performance and behavior of the system. | P0 |
| Tracing | N/A | There is no implementation for distributed tracing. | Tracing is essential for diagnosing performance issues and understanding the flow of requests across services. | P0 |
| Health Probe Completeness | `packages/common/src/heimdex_common/probes.py` | The health probes only check for basic connectivity to the dependencies. | They should be extended to check the health of the application itself. | P2 |
| Alerting and Error Reporting | N/A | There is no mention of an alerting or error reporting strategy. | Alerting and error reporting are critical for a production-ready system. | P1 |

---

## 5. :lock: Security & Compliance

| Category | File / Path | Short Description | Why it Matters | Priority |
|---|---|---|---|---|
| PII Leaks | `apps/api/src/heimdex_api/logger.py` | The current logging implementation does not include any mechanism for redacting PII. | PII should never be logged in plain text. | P1 |
| Rate Limiting | N/A | There is no rate limiting implemented on the API endpoints. | This could make the application vulnerable to denial-of-service attacks. | P1 |
| Input Sanitization | N/A | There is no explicit input sanitization being performed. | This could make the application vulnerable to injection attacks. | P2 |
| IAM Considerations | `infra/terraform/main.tf` | The IAM roles are too broad. | A more granular set of permissions should be defined to follow the principle of least privilege. | P2 |
| Dependency Vulnerabilities | `.pre-commit-config.yaml` | The pre-commit hooks do not include a check for known vulnerabilities in the dependencies. | This should be added to the CI/CD pipeline. | P1 |

---

## 6. :bricks: Schema & Data Consistency

| Category | File / Path | Short Description | Why it Matters | Priority |
|---|---|---|---|---|
| Migration Naming | `packages/common/alembic/versions` | The migration files have inconsistent naming conventions. | A consistent naming convention makes it easier to understand the history of the schema. | P3 |
| Backfill Scripts | N/A | There are no backfill scripts or cron jobs for managing data growth. | This will be important as the application scales. | P2 |

---

## 7. :rocket: Developer Experience

| Category | File / Path | Short Description | Why it Matters | Priority |
|---|---|---|---|---|
| Makefile Ergonomics | `Makefile` | The `test-integration` target in the `Makefile` has `|| true` at the end. | This can hide failures and should be removed. | P1 |
| Documentation for Key Workflows | `README.md` | The `README.md` could be improved by adding more detailed documentation for key workflows. | This would make it easier for new developers to get started with the project. | P2 |
| Environment Bootstrap | `scripts/setup-dev.sh` | The project relies on the developer having Docker and Python pre-installed. | A more complete solution would be to use a tool like `asdf` to manage the project's dependencies. | P3 |
| CLI Tools | N/A | The project does not include any CLI tools or internal debug endpoints. | These could be useful for inspecting the state of the system, running ad-hoc tasks, and debugging issues. | P3 |

---

## 8. :card_index_dividers: Documentation Debt

| Category | File / Path | Short Description | Why it Matters | Priority |
|---|---|---|---|---|
| Missing Docstrings | `apps/api`, `apps/worker` | The `api` and `worker` applications are missing docstrings in critical modules. | Docstrings are essential for understanding the code and for generating documentation. | P2 |
| README Updates | `README.md` | The main `README.md` should be updated to reflect the new architecture. | This would make it easier for new developers to understand the project. | P2 |
| Architecture Diagrams | `docs/architecture/overview.md` | The `architecture/overview.md` file would benefit from more detailed diagrams. | Diagrams are a great way to communicate complex ideas. | P3 |
| Deprecated Features | `docs/qdrant-mock-to-production.md` | The documentation refers to a deprecated `/vectors/mock` endpoint. | This should be removed to avoid confusion. | P3 |
| Placeholder Documents | `docs/architecture/sidecar-schema.md` | The `architecture/sidecar-schema.md` is a placeholder and needs to be populated. | This is a critical piece of documentation that is currently missing. | P1 |

---

## 9. :compass: Known TODO Comments in Code

| Category | File / Path | Short Description | Why it Matters | Priority |
|---|---|---|---|---|
| Configuration | `apps/api/src/heimdex_api/vectors.py` | `query_model_ver="v1", # TODO: Make this configurable` | Hardcoded values make the code less flexible and harder to maintain. | P2 |
| Documentation | `docs/architecture/sidecar-schema.md` | `TODO: Define the JSON schema for Heimdex sidecar files...` | This is a critical piece of documentation that is currently missing. | P1 |
| Observability | `docs/microstep-0.9-real-embeddings.md` | `TODO`s related to adding metrics and distributed tracing. | Metrics and tracing are essential for understanding the performance and behavior of the system. | P0 |

---

## 10. :receipt: Production Change List

| Category | File / Path | Short Description | Why it Matters | Priority |
|---|---|---|---|---|
| Redis Persistence | `deploy/docker-compose.yml` | The local development environment uses `appendonly yes` for Redis persistence. | For production, a more robust persistence and backup strategy should be implemented. | P1 |
| Debug Flags | `deploy/.env.example`, `infra/terraform/main.tf` | The `AUTH_PROVIDER` is set to `dev`. | This should be changed to `supabase` for production. | P0 |
| Logging Verbosity | N/A | The logging level is not currently configurable. | This should be made configurable so that the logging verbosity can be increased or decreased as needed. | P2 |
| Open CORS | N/A | The FastAPI application does not have any CORS middleware configured. | This should be configured to restrict access to the API from unauthorized domains. | P1 |
| Feature Toggles | N/A | There are no feature toggles in the codebase. | This would be a useful addition for enabling or disabling features in production without requiring a full deployment. | P3 |
| Environment Flags | `deploy/.env.example` | The `ENABLE_*` flags should be reviewed and set appropriately for the production environment. | This will ensure that the readiness probes are checking the correct dependencies. | P1 |
| Default Credentials | `deploy/.env.example` | The `.env.example` file contains default credentials. | These should be changed for production. | P0 |

---

## Summary

The Heimdex codebase is well-structured and follows modern software engineering practices. The use of a monorepo, containerized development, and a composable architecture provides a solid foundation for future development. However, there are several areas that need to be addressed before the project is ready for production.

### Highest-Priority Blockers

The following items are the highest-priority blockers that should be addressed before writing new business logic:

*   **P0: Implement Metrics and Tracing:** The lack of metrics and tracing is a major gap in the project's observability story. It will be very difficult to debug performance issues and understand the behavior of the system in production without this information.
*   **P0: Implement a Comprehensive Security Strategy:** The project is missing several key security features, including rate limiting, input sanitization, and dependency vulnerability scanning. These should be implemented to protect the application from attack.
*   **P1: Add Unit and Integration Tests:** The project is missing unit and integration tests for the `api` and `worker` applications. This makes it difficult to ensure the quality of the code and to prevent regressions.
*   **P1: Remove `|| true` from CI/CD Pipeline:** The use of `|| true` in the CI/CD pipeline is hiding failures. This should be removed so that the team is aware of any issues with the build.
*   **P1: Configure Production Environment:** The project is not yet configured for production. The `AUTH_PROVIDER` needs to be changed to `supabase`, and the default credentials need to be replaced.

Once these high-priority items have been addressed, the team can move on to the lower-priority items, such as improving the developer experience and adding more documentation.
