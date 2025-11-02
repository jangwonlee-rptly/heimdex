# Containerized CI/CD - Complete Guide

## Overview

**All CI/CD operations now run in Docker containers** for maximum reproducibility and consistency.

### Benefits

✅ **Reproducible** - Same environment everywhere (local, CI, production)
✅ **Isolated** - No dependency conflicts with host system
✅ **Fast Onboarding** - No local tool installation required
✅ **Consistent** - Exact same versions across all environments
✅ **Portable** - Works on any machine with Docker

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                  Developer Machine                    │
│  ┌────────────────────────────────────────────────┐ │
│  │         make lint / test / fmt                 │ │
│  └────────────────────┬───────────────────────────┘ │
│                       ▼                              │
│  ┌────────────────────────────────────────────────┐ │
│  │      docker compose run dev <command>          │ │
│  │                                                │ │
│  │  - All tools pre-installed                    │ │
│  │  - Source code mounted                        │ │
│  │  │  - Access to all services                   │ │
│  └────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────┐
│                    GitHub Actions                     │
│  ┌────────────────────────────────────────────────┐ │
│  │         Lint / Test / Build Jobs               │ │
│  └────────────────────┬───────────────────────────┘ │
│                       ▼                              │
│  ┌────────────────────────────────────────────────┐ │
│  │      docker run heimdex-dev:ci <command>       │ │
│  │                                                │ │
│  │  - Built from Dockerfile.dev                  │ │
│  │  - All tools included                         │ │
│  │  - Connected to service network               │ │
│  └────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

## Components

### 1. Development Container (`Dockerfile.dev`)

**Purpose:** Contains all development and CI tools plus project dependencies

**Tools Installed:**

- Python 3.11
- UV package manager
- ruff (linter + formatter)
- black (formatter)
- mypy (type checker)
- pytest (test runner)
- pre-commit
- Git and build tools

**Project Dependencies:**

- All dependencies from `heimdex-common`, `heimdex-api`, and `heimdex-worker`
- Installed in editable mode during image build
- Packages installed to `/usr/local/lib/python3.11/site-packages/`
- Source code provided by volume mount at runtime

**Key Features:**

- **Zero runtime dependency installation** - all deps baked into image
- System-wide tool installation (`uv pip install --system`)
- Non-root user (devuser)
- Optimized layer caching for fast rebuilds
- Editable installs with volume-mounted source code

### 2. Docker Compose Service (`dev`)

**Purpose:** Run dev container with project mounted

**Configuration:**

```yaml
services:
  dev:
    build:
      context: ..
      dockerfile: Dockerfile.dev
    volumes:
      - ..:/workspace:cached  # Project source mounted
    working_dir: /workspace
    networks:
      - heimdex  # Access to pg, redis, qdrant
    depends_on:
      - pg
      - redis
      - qdrant
```

**Access Pattern:**

```bash
# Run any command in the container
docker compose -f deploy/docker-compose.yml run --rm dev <command>

# Or use Make targets (recommended)
make lint
make test
make fmt
```

### 3. Makefile Integration

All development commands now run in containers:

```makefile
# Development container commands
DEV_RUN := docker compose -f deploy/docker-compose.yml run --rm dev

# All targets use containers
lint:
    @$(DEV_RUN) ruff check --output-format=github .

test-unit:
    @$(DEV_RUN) sh -c "cd packages/common && pytest tests/"

migrate:
    @$(DEV_RUN) sh -c "cd packages/common && alembic upgrade head"
```

### 4. CI Workflow Integration

GitHub Actions workflows use the same container with dependencies pre-installed:

```yaml
- name: Build dev container
  run: docker build -t heimdex-dev:ci -f Dockerfile.dev .
  # This builds the image with ALL dependencies installed
  # No separate install step needed!

- name: Run linting
  run: |
    docker run --rm -v $(pwd):/workspace -w /workspace heimdex-dev:ci \
      ruff check .

- name: Run tests
  run: |
    docker run --rm --network deploy_heimdex \
      -v $(pwd):/workspace -w /workspace \
      heimdex-dev:ci sh -c "cd packages/common && pytest tests/"
```

**Key Improvement:** Dependencies are baked into the image during build, eliminating the need for a separate install step in CI. This makes workflows faster and more reliable.

## Usage Guide

### Setup

```bash
# One-time setup: build the dev container with all dependencies
make setup

# What it does:
# 1. Builds Dockerfile.dev with all dev tools
# 2. Copies project files into image
# 3. Installs all project dependencies in editable mode
# 4. All dependencies are now baked into the image
```

**Note:** After modifying dependencies in `pyproject.toml`, rebuild with `make dev-build`

### Daily Development

```bash
# Lint code (runs in container)
make lint

# Format code (runs in container)
make fmt

# Type check (runs in container)
make typecheck

# Run tests (runs in container)
make test

# Run migrations (runs in container)
make migrate

# Everything runs in containers!
```

### Interactive Shell

```bash
# Get a shell inside the dev container
make dev-shell

# Now you're inside the container:
devuser@abc123:/workspace$ ruff check .
devuser@abc123:/workspace$ pytest tests/
devuser@abc123:/workspace$ python -c "import heimdex_common"
```

### Custom Commands

```bash
# Run any command in the dev container
make dev-run CMD="python scripts/my_script.py"

# Or directly via docker compose
docker compose -f deploy/docker-compose.yml run --rm dev python scripts/my_script.py
```

## CI/CD Workflow

### Lint Job

```yaml
- Build dev container (heimdex-dev:ci) with all dependencies
- Run ruff lint in container
- Run ruff format check in container
- Run mypy type check in container
```

**Runtime:** ~1.5-2 minutes (faster without separate install step)

### Unit Tests Job

```yaml
- Build dev container with all dependencies
- Run pytest unit tests in container
```

**Runtime:** ~1.5-2 minutes (faster without separate install step)

### Integration Tests Job

```yaml
- Start services (pg, redis, qdrant) with docker compose
- Build dev container with all dependencies
- Run migrations in container (connected to services network)
- Start API and worker services
- Run E2E tests in container (connected to all services)
- Cleanup
```

**Runtime:** ~8-12 minutes (faster without separate install step)

### Docker Build Job

```yaml
- Build API image
- Build Worker image
- Validate images
```

**Runtime:** ~5-10 minutes per image

## Environment Variables

### Local Development

Set in `deploy/.env`:

```bash
PGHOST=localhost  # Or 'pg' if running in dev container
PGPORT=5432
PGUSER=heimdex
PGPASSWORD=heimdex
PGDATABASE=heimdex
REDIS_URL=redis://localhost:6379/0
QDRANT_URL=http://localhost:6333
```

### CI Environment

Set via docker run `-e` flags:

```bash
docker run --rm --network deploy_heimdex \
  -e PGHOST=pg \
  -e PGPORT=5432 \
  -e PGUSER=heimdex \
  -e PGPASSWORD=heimdex \
  -e REDIS_URL=redis://redis:6379/0 \
  heimdex-dev:ci <command>
```

## Networking

### Service Discovery

All containers are on the same network (`heimdex`):

| Service | Hostname | Port |
|---------|----------|------|
| PostgreSQL | `pg` | 5432 |
| Redis | `redis` | 6379 |
| Qdrant | `qdrant` | 6333 |
| API | `api` | 8000 |
| Worker | `worker` | - |
| Dev Container | - | - |

### Connection Examples

```python
# Inside dev container, connect to services:
PGHOST=pg            # Not localhost!
REDIS_URL=redis://redis:6379/0
QDRANT_URL=http://qdrant:6333
```

## Troubleshooting

### Issue: "Cannot connect to database"

**Cause:** Using `localhost` instead of service name

**Solution:**

```bash
# Wrong (when running in container)
PGHOST=localhost

# Correct (when running in container)
PGHOST=pg
```

### Issue: "ruff: command not found"

**Cause:** Trying to run tools on host instead of in container

**Solution:**

```bash
# Wrong
ruff check .

# Correct
make lint
# or
docker compose -f deploy/docker-compose.yml run --rm dev ruff check .
```

### Issue: "Dev container build failed"

**Cause:** Docker build cache issue or network problem

**Solution:**

```bash
# Rebuild without cache
docker compose -f deploy/docker-compose.yml build --no-cache dev

# Or
docker build --no-cache -t heimdex-dev:local -f Dockerfile.dev .
```

### Issue: "Tests can't find modules"

**Cause:** Dev container image is outdated or dependencies changed

**Solution:**

```bash
# Rebuild the dev container image
make dev-build

# This will rebuild the image with all current dependencies
# Dependencies are baked into the image, not installed at runtime
```

## Performance Optimization

### 1. Docker Layer Caching

The dev container is built with optimized layers:

- Base image (python:3.11-slim)
- System dependencies (git, curl, build-essential)
- UV installation
- Dev tool installation (ruff, mypy, pytest, pre-commit)
- **Project dependencies** (heimdex-common, heimdex-api, heimdex-worker)
- **Source code mounted at runtime** (not in image)

**Result:** Fast rebuilds (~30 seconds when only source code changes)

**Smart Caching:** Docker only rebuilds layers that changed:

- Code changes: Only remount volume (instant)
- Dependency changes: Rebuild from dependency layer (~1-2 minutes)
- Tool changes: Rebuild from tool layer (~30 seconds)

### 2. Volume Caching

Source code is mounted with `:cached` flag for better performance:

```yaml
volumes:
  - ..:/workspace:cached
```

**Result:**

- Better I/O performance on macOS
- Source code changes instantly available in container
- No image rebuild needed for code changes

### 3. Dependency Persistence

Dependencies are **baked into the container image**:

```bash
make dev-build  # Builds image with dependencies
make test       # Uses dependencies from image (no install)
make lint       # Uses dependencies from image (no install)
```

**Benefits:**

- Zero runtime installation overhead
- Guaranteed consistency across all container runs
- Faster CI/CD pipeline (no install step needed)

## Comparison: Before vs After

| Aspect | Before (Local Install) | After (Containerized) |
|--------|----------------------|---------------------|
| **Setup** | Install Python, UV, tools | `make setup` (builds container) |
| **Dependencies** | Virtual environment (.venv) | Container with system packages |
| **Tool Versions** | Varies by machine | Exact same (Dockerfile.dev) |
| **CI Consistency** | Different from local | Identical to local |
| **Onboarding** | 10+ steps | 1 command |
| **Environment Conflicts** | Possible | Impossible (isolated) |
| **Reproducibility** | Medium | Perfect |

## Best Practices

### 1. Always Use Make Targets

```bash
# Good
make lint
make test
make migrate

# Avoid (requires knowledge of docker compose)
docker compose -f deploy/docker-compose.yml run --rm dev ruff check .
```

### 2. Rebuild After Dockerfile Changes

```bash
# After modifying Dockerfile.dev
make dev-build

# Or
docker compose -f deploy/docker-compose.yml build dev
```

### 3. Use dev-shell for Interactive Work

```bash
# Get a shell
make dev-shell

# Run multiple commands interactively
devuser@abc123:/workspace$ ruff check .
devuser@abc123:/workspace$ pytest tests/
devuser@abc123:/workspace$ python -m mymodule
```

### 4. Clean Up Regularly

```bash
# Remove stopped containers
docker compose -f deploy/docker-compose.yml down

# Remove volumes
docker compose -f deploy/docker-compose.yml down -v

# Full cleanup
make clean
docker system prune -af
```

## Future Enhancements

### Planned Improvements

1. **Multi-stage Caching**
   - Cache dependencies separately
   - Even faster rebuilds

2. **Dev Container Spec**
   - Add `.devcontainer/devcontainer.json`
   - VSCode/Cursor integration

3. **Pre-built Images**
   - Push dev image to registry
   - Skip build in CI (pull instead)

4. **Watch Mode**
   - Auto-run tests on file changes
   - Live reload in container

## Summary

### ✅ What Changed

- **All commands run in containers** (lint, test, migrate, etc.)
- **Same environment everywhere** (local, CI, production)
- **No local tool installation** needed
- **Perfect reproducibility**

### 📝 Migration Checklist

- [x] Created `Dockerfile.dev` with all tools
- [x] Added `dev` service to docker-compose.yml
- [x] Updated Makefile to use containers
- [x] Updated CI workflows to use containers
- [x] Documented containerized approach

### 🚀 Quick Start

```bash
# Setup (builds container)
make setup

# Daily development (all in containers)
make lint
make test
make fmt

# Everything just works!
```

---

**Status:** ✅ Complete and Production-Ready
**Last Updated:** 2025-11-01
**Container Base:** python:3.11-slim
**Package Manager:** UV (system-wide in containers)
