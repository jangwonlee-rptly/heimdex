# UV Integration - Corrected Implementation

## Overview

Heimdex uses **UV** for Python package management with environment-specific patterns:

- **Local Development:** UV with virtual environments
- **Docker Containers:** UV with `--system` flag (no virtual environment)
- **CI/CD:** UV with `--system` flag (no virtual environment)

## ✅ Corrected Implementation

### 1. Local Development (Virtual Environments)

**Makefile** - All local targets use UV with virtual environments:

```makefile
# Install dependencies (no --system flag)
install:
 @cd packages/common && $(UV) pip install -e ".[test]"
 @cd apps/api && $(UV) pip install -e .
 @cd apps/worker && $(UV) pip install -e .

# Run tools via uv run
lint:
 @$(UV) run ruff check --output-format=github .

fmt:
 @$(UV) run ruff check --fix .
 @$(UV) run ruff format .

typecheck:
 @$(UV) run mypy packages/common/src apps/api/src apps/worker/src \
  --ignore-missing-imports --no-warn-unused-ignores

# Run tests via uv run
test-unit:
 @cd packages/common && $(UV) run pytest tests/ -v --tb=short \
  --ignore=tests/test_embeddings_e2e.py

# Run migrations via uv run
migrate:
 @cd packages/common && $(UV) run alembic upgrade head
```

**Key Pattern:**

- `uv pip install -e .` (creates/uses virtual environment)
- `uv run <command>` (runs command in virtual environment)

**setup-dev.sh** - Uses virtual environments:

```bash
# Install dependencies (no --system flag)
cd packages/common && uv pip install -e ".[test]"
cd apps/api && uv pip install -e .
cd apps/worker && uv pip install -e .

# Install pre-commit via uv run
uv run pre-commit install
```

**run-tests.sh** - Uses virtual environments:

```bash
# Run tests via uv run
cd packages/common
uv run pytest tests/ -v --tb=short
```

---

### 2. Docker Containers (System-Wide Installation)

**Dockerfiles** - Use `--system` flag (no virtual environment):

```dockerfile
FROM python:3.11-slim

# Install uv
RUN pip install --no-cache-dir uv

# Install dependencies system-wide
RUN uv pip install --system --no-cache --quiet /app/packages/common && \
    uv pip install --system --no-cache --quiet .

# Run application directly (no uv run)
CMD ["uvicorn", "heimdex_api.main:app", "--host", "0.0.0.0", "--port", "${PORT}"]
```

**Key Pattern:**

- `uv pip install --system` (installs to system Python)
- `--no-cache` (reduces image size)
- Direct command execution (no `uv run`)

**Why `--system` in containers:**

- No virtual environment overhead
- Simpler PATH management
- Standard practice for containerized apps
- Smaller image size

---

### 3. CI/CD (System-Wide Installation)

**GitHub Actions** - Uses `--system` flag:

```yaml
- name: Install uv
  run: |
    curl -LsSf https://astral.sh/uv/install.sh | sh
    echo "$HOME/.cargo/bin" >> $GITHUB_PATH

- name: Install dependencies
  run: |
    cd packages/common
    uv pip install --system -e ".[test]"

- name: Run ruff (lint)
  run: |
    uv pip install --system ruff
    ruff check --output-format=github .

- name: Run unit tests
  run: |
    cd packages/common
    pytest tests/ -v --tb=short
```

**Key Pattern:**

- `uv pip install --system` (installs to system Python)
- Direct command execution (no `uv run`)
- Tools installed globally in CI environment

**Why `--system` in CI:**

- Faster execution (no virtual environment creation)
- Simpler dependency caching
- Standard practice for CI environments
- Matches Docker build pattern

---

## 📊 Environment Comparison

| Aspect | Local Development | Docker | CI/CD |
|--------|------------------|--------|-------|
| **UV Flag** | (none) | `--system` | `--system` |
| **Virtual Env** | ✅ Yes | ❌ No | ❌ No |
| **Command Prefix** | `uv run` | Direct | Direct |
| **Install Command** | `uv pip install -e .` | `uv pip install --system .` | `uv pip install --system .` |
| **Run Tests** | `uv run pytest` | `pytest` | `pytest` |
| **Run Tools** | `uv run ruff` | `ruff` | `ruff` |

---

## 🔍 Why This Pattern?

### Local Development (Virtual Environments)

**Advantages:**

- ✅ Isolation from system Python
- ✅ Multiple projects can coexist
- ✅ Easy to reset (delete .venv)
- ✅ Standard Python development practice
- ✅ Dependency conflicts avoided

**Example:**

```bash
# Setup creates virtual environment
make setup

# Install adds to virtual environment
make install

# Run commands use virtual environment
make lint
make test
```

### Containers (System-Wide)

**Advantages:**

- ✅ Single-purpose environment
- ✅ No virtual environment overhead
- ✅ Simpler Dockerfile
- ✅ Smaller image size
- ✅ Faster startup

**Example:**

```dockerfile
# Install to system Python
RUN uv pip install --system --no-cache -e .

# Run directly
CMD ["uvicorn", "app.main:app"]
```

### CI/CD (System-Wide)

**Advantages:**

- ✅ Ephemeral environment (destroyed after job)
- ✅ Faster execution
- ✅ Simpler caching strategy
- ✅ Matches production (Docker) pattern
- ✅ Standard CI practice

**Example:**

```yaml
# Install to system Python
- run: uv pip install --system -e .

# Run directly
- run: pytest tests/
```

---

## 🚀 Usage Examples

### Local Development Workflow

```bash
# Initial setup (creates virtual environment)
make setup

# Install dependencies (into virtual environment)
make install

# Run linting (uses virtual environment)
make lint

# Run tests (uses virtual environment)
make test

# Run migrations (uses virtual environment)
make migrate

# Clean everything including virtual environment
make clean
```

### Docker Workflow

```bash
# Build images (uses --system inside)
make build

# Images have dependencies installed system-wide
docker compose up

# No virtual environment in containers
docker compose exec api python -c "import sys; print(sys.prefix)"
# Output: /usr/local (system Python)
```

### CI/CD Workflow

```bash
# CI automatically:
# 1. Installs UV
# 2. Installs dependencies with --system
# 3. Runs tests directly

# Triggered on:
git push origin feature-branch
```

---

## 📝 File Changes Summary

### ✅ Updated for Virtual Environments

1. **Makefile**
   - Removed `--system` from all targets
   - Added `uv run` prefix for commands
   - Updated migrations to use `uv run`

2. **scripts/setup-dev.sh**
   - Removed `--system` from install commands
   - Changed to `uv run pre-commit install`

3. **scripts/run-tests.sh**
   - Changed to `uv run pytest`

### ✅ Already Correct (System-Wide)

1. **apps/api/Dockerfile** ✅
   - Uses `uv pip install --system`

2. **apps/worker/Dockerfile** ✅
   - Uses `uv pip install --system`

3. **.github/workflows/ci.yml** ✅
   - Uses `uv pip install --system`

### ✅ Environment-Agnostic

1. **scripts/wait-for-services.sh** ✅
   - No Python package management

2. **scripts/validate-config.sh** ✅
   - No Python package management

---

## 🧪 Verification

### Verify Local Uses Virtual Environment

```bash
# After make setup
cd packages/common

# Check for virtual environment
ls .venv/  # Should exist

# Check uv uses it
uv pip list
# Should show packages from virtual environment

# Verify uv run uses it
uv run python -c "import sys; print(sys.prefix)"
# Should show .venv path
```

### Verify Docker Uses System Python

```bash
# Build and start
make build
docker compose up -d

# Check Python environment
docker compose exec api python -c "import sys; print(sys.prefix)"
# Output: /usr/local (not a virtual environment)

# Check packages are system-wide
docker compose exec api pip list
# Shows system-wide packages
```

### Verify CI Uses System Python

```bash
# Check GitHub Actions logs after push

# Look for:
# - "uv pip install --system" commands
# - No virtual environment creation
# - Direct pytest/ruff execution
```

---

## 🔧 Troubleshooting

### Issue: "Package not found" locally

**Cause:** Virtual environment not activated or packages not installed

**Solution:**

```bash
# Re-install
make install

# Or use uv run
uv run pytest  # Instead of pytest directly
```

### Issue: "Package not found" in Docker

**Cause:** Missing `--system` flag or build cache issue

**Solution:**

```bash
# Rebuild without cache
docker compose build --no-cache

# Verify Dockerfile uses --system
grep "uv pip install" apps/*/Dockerfile
# Should show: uv pip install --system
```

### Issue: CI fails with package errors

**Cause:** Missing `--system` flag in workflow

**Solution:**

```bash
# Check workflow file
grep "uv pip install" .github/workflows/ci.yml
# Should show: uv pip install --system
```

---

## 📚 Documentation Updated

### Created/Updated Files

1. **Makefile** ✅
   - Local development uses virtual environments
   - All commands use `uv run`

2. **scripts/setup-dev.sh** ✅
   - Creates virtual environment
   - Installs to virtual environment

3. **scripts/run-tests.sh** ✅
   - Uses `uv run pytest`

4. **UV_INTEGRATION_CORRECTED.md** ✅ (this file)
   - Complete corrected documentation
   - Environment-specific patterns
   - Verification steps

### Verified Correct (No Changes Needed)

1. **apps/api/Dockerfile** ✅
2. **apps/worker/Dockerfile** ✅
3. **.github/workflows/ci.yml** ✅
4. **.github/workflows/infra.yml** ✅

---

## ✅ Summary

### What's Correct Now

| Component | Environment Type | UV Pattern | Status |
|-----------|-----------------|------------|---------|
| Makefile | Local | Virtual env | ✅ Fixed |
| setup-dev.sh | Local | Virtual env | ✅ Fixed |
| run-tests.sh | Local | Virtual env | ✅ Fixed |
| API Dockerfile | Container | System-wide | ✅ Already correct |
| Worker Dockerfile | Container | System-wide | ✅ Already correct |
| CI Workflow | CI/CD | System-wide | ✅ Already correct |

### Key Takeaway

```
Local Development:  uv pip install -e .  +  uv run <command>
Docker Containers:  uv pip install --system .  +  <command>
CI/CD:             uv pip install --system .  +  <command>
```

---

**Last Updated:** 2025-11-01
**Status:** ✅ Corrected
**UV Version:** Latest (from official installer)
**Python Version:** 3.11
