.PHONY: lint fmt setup up down logs health readyz reset test-job test-job-fail check-job migrate makemigration migration-history

lint:
	@echo "placeholder for repository linting (ruff, mypy)"

fmt:
	@echo "placeholder for code formatting (black)"

setup:
	@echo "placeholder for environment bootstrap"

# Database migrations
migrate:
	@echo "Running Alembic migrations..."
	@cd packages/common && alembic upgrade head

makemigration:
	@echo "Generating new Alembic migration (autogenerate)..."
	@cd packages/common && alembic revision --autogenerate

migration-history:
	@echo "Showing Alembic migration history..."
	@cd packages/common && alembic history --verbose

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
	@echo "Creating a test job..."
	@curl -X POST http://localhost:8000/jobs \
		-H "Content-Type: application/json" \
		-d '{"type": "mock_process"}' | tee /tmp/heimdex_job.json
	@echo ""

test-job-fail:
	@echo "Creating a test job that will fail at 'analyzing' stage..."
	@curl -X POST http://localhost:8000/jobs \
		-H "Content-Type: application/json" \
		-d '{"type": "mock_process", "fail_at_stage": "analyzing"}' | tee /tmp/heimdex_job.json
	@echo ""

check-job:
	@if [ ! -f /tmp/heimdex_job.json ]; then \
		echo "No job ID found. Run 'make test-job' first."; \
		exit 1; \
	fi
	@JOB_ID=$$(cat /tmp/heimdex_job.json | grep -o '"job_id":"[^"]*"' | cut -d'"' -f4); \
	echo "Checking status for job: $$JOB_ID"; \
	curl -s http://localhost:8000/jobs/$$JOB_ID | python3 -m json.tool
