# Heimdex Helper Scripts

This directory contains helper scripts for development, testing, and CI/CD operations.

## Available Scripts

### `setup-dev.sh`

Sets up the complete development environment.

**Usage:**

```bash
./scripts/setup-dev.sh
```

**What it does:**

- Checks Python version (requires 3.11+)
- Installs uv package manager if not present
- Installs all Python dependencies
- Sets up pre-commit hooks
- Creates `.env` from `.env.example` if missing

**When to use:**

- First time setting up the project
- After pulling major changes
- When dependencies are out of sync

---

### `wait-for-services.sh`

Waits for all required services to be ready before running tests or other operations.

**Usage:**

```bash
./scripts/wait-for-services.sh
```

**Environment variables:**

- `TIMEOUT` - Maximum wait time in seconds (default: 60)
- `PGHOST`, `PGPORT`, `PGUSER` - PostgreSQL connection
- `REDIS_HOST`, `REDIS_PORT` - Redis connection
- `QDRANT_URL` - Qdrant URL
- `API_URL` - API URL
- `WAIT_FOR_API` - Set to "true" to wait for API (optional)

**What it does:**

- Waits for PostgreSQL to be ready
- Waits for Redis to be ready
- Waits for Qdrant to be ready
- Optionally waits for API to be ready

**When to use:**

- In CI pipelines before running tests
- In local testing when services are starting
- In docker-compose startup scripts

---

### `run-tests.sh`

Runs tests with proper setup and validation.

**Usage:**

```bash
./scripts/run-tests.sh [unit|integration|all]
```

**Arguments:**

- `unit` - Run unit tests only
- `integration` - Run integration tests only
- `all` - Run all tests (default)

**What it does:**

- Validates environment setup
- Runs requested test suite(s)
- Reports results with clear output

**When to use:**

- Before committing code
- In CI pipelines
- When validating changes locally

---

### `validate-config.sh`

Validates all configuration files for completeness and correctness.

**Usage:**

```bash
./scripts/validate-config.sh
```

**What it does:**

- Checks for required `.env` file
- Validates all required environment variables
- Validates `docker-compose.yml` syntax
- Checks for required `pyproject.toml` files
- Checks for required Dockerfile files

**When to use:**

- Before starting services
- In CI pipelines
- When debugging configuration issues
- After making configuration changes

---

## Integration with Makefile

These scripts are also accessible via Makefile targets:

```bash
make setup          # Runs setup-dev.sh
make test           # Uses run-tests.sh
make test-unit      # Runs unit tests
make test-integration # Runs integration tests
```

## CI/CD Usage

These scripts are used in GitHub Actions workflows:

- `.github/workflows/ci.yml` - Uses `wait-for-services.sh` and testing scripts
- `.github/workflows/infra.yml` - Uses validation scripts

## Adding New Scripts

When adding new scripts:

1. Place them in this directory
2. Make them executable: `chmod +x scripts/your-script.sh`
3. Add a shebang: `#!/usr/bin/env bash`
4. Use `set -euo pipefail` for safety
5. Add clear comments and usage instructions
6. Update this README
7. Consider adding a Makefile target
