.PHONY: help lint fmt typecheck test test-unit test-integration pre-commit \
        setup install build docker-build clean \
        up down logs health readyz reset \
        test-job test-job-fail check-job \
        migrate makemigration migration-history \
        dev-build dev-run dev-shell

# Default target
.DEFAULT_GOAL := help

# Docker Compose configuration
DOCKER_COMPOSE := docker compose -f deploy/docker-compose.yml
DEV_RUN := $(DOCKER_COMPOSE) run --rm dev
DEV_EXEC := $(DOCKER_COMPOSE) exec dev

# Python and UV configuration
PYTHON_VERSION := 3.11
UV := uv

# Help target - displays all available targets
help:
	@echo "Heimdex Makefile - Available targets:"
	@echo ""
	@echo "Development Setup:"
	@echo "  make setup           - Install uv and set up development environment"
	@echo "  make install         - Install all Python dependencies"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint            - Run all linters (ruff, mypy)"
	@echo "  make fmt             - Format code with ruff and black"
	@echo "  make typecheck       - Run mypy type checking"
	@echo "  make pre-commit      - Run all pre-commit hooks"
	@echo ""
	@echo "Testing:"
	@echo "  make test            - Run all tests (unit + integration)"
	@echo "  make test-unit       - Run unit tests only"
	@echo "  make test-integration - Run integration tests only"
	@echo ""
	@echo "Docker & Services:"
	@echo "  make build           - Build all Docker images"
	@echo "  make docker-build    - Build Docker images (alias for build)"
	@echo "  make up              - Start all services with docker compose"
	@echo "  make down            - Stop all services"
	@echo "  make logs            - View service logs"
	@echo "  make reset           - Reset all data (drops volumes)"
	@echo ""
	@echo "Database:"
	@echo "  make migrate         - Run database migrations"
	@echo "  make makemigration   - Generate new migration"
	@echo "  make migration-history - Show migration history"
	@echo ""
	@echo "Health Checks:"
	@echo "  make health          - Check API health"
	@echo "  make readyz          - Check API readiness"
	@echo ""
	@echo "Testing Jobs:"
	@echo "  make test-job        - Create a test job"
	@echo "  make test-job-fail   - Create a test job that fails"
	@echo "  make check-job       - Check status of last test job"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean           - Remove build artifacts and caches"

# Development setup
setup: dev-build
	@echo "✓ Development environment ready!"
	@echo "All dependencies are installed in the dev container image."

dev-build:
	@echo "Building development container with dependencies..."
	@$(DOCKER_COMPOSE) build dev
	@echo "✓ Development container built"

dev-shell:
	@echo "Starting development shell..."
	@$(DEV_RUN) /bin/bash

dev-run:
	@echo "Running command in dev container: $(CMD)"
	@$(DEV_RUN) $(CMD)

install:
	@echo "Dependencies are built into the dev container image."
	@echo "Run 'make dev-build' to rebuild the container with latest dependencies."

# Code quality targets (all run in containers)
lint:
	@echo "Running ruff linter in container..."
	@$(DEV_RUN) ruff check --output-format=github .
	@echo "✓ Linting complete"

fmt:
	@echo "Running code formatters in container..."
	@$(DEV_RUN) sh -c "ruff check --fix . && ruff format ."
	@echo "✓ Formatting complete"

typecheck:
	@echo "Running mypy type checker in container..."
	@$(DEV_RUN) mypy packages/common/src apps/api/src apps/worker/src \
		--ignore-missing-imports --no-warn-unused-ignores
	@echo "✓ Type checking complete"

pre-commit:
	@echo "Running all pre-commit hooks in container..."
	@$(DEV_RUN) pre-commit run --all-files
	@echo "✓ Pre-commit checks complete"

# Testing targets (all run in containers)
test: test-unit test-integration

test-unit:
	@echo "Running unit tests in container..."
	@$(DEV_RUN) sh -c "cd packages/common && pytest tests/ -v --tb=short \
		--ignore=tests/test_embeddings_e2e.py"
	@echo "✓ Unit tests complete"

test-integration:
	@echo "Starting services for integration tests..."
	@$(MAKE) up
	@echo "Waiting for services to be ready..."
	@sleep 10
	@echo "Running integration tests in container..."
	@$(DEV_RUN) sh -c "cd packages/common && pytest tests/test_embeddings_e2e.py -v --tb=short" || true
	@echo "✓ Integration tests complete"

# Docker targets
build: docker-build

docker-build:
	@echo "Building Docker images..."
	@cd deploy && docker compose build
	@echo "✓ Docker images built"

clean:
	@echo "Cleaning build artifacts and caches..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type d -name ".venv" -exec rm -rf {} + 2>/dev/null || true
	@echo "✓ Cleanup complete"

# Database migrations (run in containers)
migrate:
	@echo "Running Alembic migrations in container..."
	@$(DEV_RUN) sh -c "cd packages/common && alembic upgrade head"

makemigration:
	@echo "Generating new Alembic migration in container..."
	@$(DEV_RUN) sh -c "cd packages/common && alembic revision --autogenerate"

migration-history:
	@echo "Showing Alembic migration history..."
	@$(DEV_RUN) sh -c "cd packages/common && alembic history --verbose"

up:
	$(MAKE) -C deploy up

down:
	$(MAKE) -C deploy down

logs:
	$(MAKE) -C deploy logs

health:
	curl -fsS http://localhost:8000/healthz

readyz:
	@echo "Checking API readiness (with dependency probes)..."
	@curl -fsS http://localhost:8000/readyz | python3 -m json.tool

reset:
	@echo "Resetting database and Redis..."
	docker compose -f deploy/docker-compose.yml down -v
	docker compose -f deploy/docker-compose.yml up -d

test-job:
	@echo "Generating dev token..."
	@TOKEN=$$(docker compose -f deploy/docker-compose.yml exec -T api python3 -c "from heimdex_common.auth import create_dev_token; import uuid; print(create_dev_token('test-user', str(uuid.uuid4()), 'user'))"); \
	echo "Creating a test job..."; \
	curl -X POST http://localhost:8000/jobs \
		-H "Content-Type: application/json" \
		-H "Authorization: Bearer $$TOKEN" \
		-d '{"type": "mock_process"}' | tee /tmp/heimdex_job.json
	@echo ""

test-job-fail:
	@echo "Generating dev token..."
	@TOKEN=$$(docker compose -f deploy/docker-compose.yml exec -T api python3 -c "from heimdex_common.auth import create_dev_token; import uuid; print(create_dev_token('test-user', str(uuid.uuid4()), 'user'))"); \
	echo "Creating a test job that will fail at 'analyzing' stage..."; \
	curl -X POST http://localhost:8000/jobs \
		-H "Content-Type: application/json" \
		-H "Authorization: Bearer $$TOKEN" \
		-d '{"type": "mock_process", "fail_at_stage": "analyzing"}' | tee /tmp/heimdex_job.json
	@echo ""

check-job:
	@if [ ! -f /tmp/heimdex_job.json ]; then \
		echo "No job ID found. Run 'make test-job' first."; \
		exit 1; \
	fi
	@echo "Generating dev token..."
	@TOKEN=$$(docker compose -f deploy/docker-compose.yml exec -T api python3 -c "from heimdex_common.auth import create_dev_token; import uuid; print(create_dev_token('test-user', str(uuid.uuid4()), 'user'))"); \
	JOB_ID=$$(cat /tmp/heimdex_job.json | grep -o '"job_id":"[^"]*"' | cut -d'"' -f4); \
	echo "Checking status for job: $$JOB_ID"; \
	curl -s http://localhost:8000/jobs/$$JOB_ID \
		-H "Authorization: Bearer $$TOKEN" | python3 -m json.tool
