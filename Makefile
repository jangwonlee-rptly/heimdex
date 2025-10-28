.PHONY: lint fmt setup up down logs

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
