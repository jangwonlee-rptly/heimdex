.PHONY: lint fmt setup up down logs health

lint:
	@echo "placeholder for repository linting (ruff, mypy)"

fmt:
	@echo "placeholder for code formatting (black)"

setup:
	@echo "placeholder for environment bootstrap"

up:
	$(MAKE) -C deploy up

down:
	$(MAKE) -C deploy down

logs:
	$(MAKE) -C deploy logs

health:
	curl -fsS http://localhost:8000/healthz
