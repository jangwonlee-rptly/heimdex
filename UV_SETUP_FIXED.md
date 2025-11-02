# UV Setup - Final Fix Summary

## Problem Identified

The initial UV integration had two critical issues:

1. **Wrong installation pattern for local development** - Was using `--system` flag locally
2. **Path resolution issue** - Was changing directories before installing, breaking local package resolution

## Solutions Implemented

### 1. Virtual Environment Creation

**Added:** Automatic virtual environment creation before installation

```makefile
# Makefile
install:
 @test -d .venv || $(UV) venv  # Create venv if it doesn't exist
 @$(UV) pip install -e "packages/common[test]"
 ...
```

```bash
# scripts/setup-dev.sh
if [ ! -d ".venv" ]; then
    uv venv
fi
```

### 2. Path Resolution Fix

**Before (BROKEN):**

```makefile
install:
 @cd packages/common && $(UV) pip install -e ".[test]"
 @cd apps/api && $(UV) pip install -e .  # Can't find heimdex-common!
```

**After (FIXED):**

```makefile
install:
 @$(UV) pip install -e "packages/common[test]"  # From project root
 @$(UV) pip install -e "apps/api"               # Can find heimdex-common!
 @$(UV) pip install -e "apps/worker"
```

**Why this works:**

- Running from project root allows UV to resolve local dependencies
- `apps/api` depends on `heimdex-common` via relative path
- UV can find `packages/common` when running from root

### 3. Tool Installation Pattern

Tools like ruff and mypy are installed on-demand into the virtual environment:

```makefile
lint:
 @$(UV) pip install ruff 2>/dev/null || true  # Install if needed
 @$(UV) run ruff check .                      # Run via uv run
```

## Final Working Pattern

### Environment-Specific Usage

| Environment | Create Env | Install Packages | Run Commands |
|------------|------------|------------------|--------------|
| **Local** | `uv venv` | `uv pip install -e .` | `uv run <cmd>` |
| **Docker** | (none) | `uv pip install --system .` | `<cmd>` |
| **CI/CD** | (none) | `uv pip install --system .` | `<cmd>` |

### Commands That Work Now

```bash
# Setup (creates .venv, installs all packages)
make setup

# Install dependencies
make install

# Linting (installs ruff, runs it via uv run)
make lint

# Testing (runs pytest via uv run)
make test

# Migrations (runs alembic via uv run)
make migrate

# All commands use the virtual environment automatically!
```

## Verification

### Test Installation

```bash
$ make install
Installing Python dependencies with uv (in virtual environment)...
Creating virtual environment at: .venv ✓
Installed 77 packages in 256ms ✓
Installed 11 packages in 10ms ✓
Installed 1 package in 0.76ms ✓
✓ Dependencies installed
```

### Test Lint

```bash
$ make lint
Running ruff linter...
Installed ruff ✓
Found 6 linting issues ✓  # Expected!
```

### Verify Virtual Environment

```bash
$ ls .venv/
bin  include  lib  pyvenv.cfg  # Virtual environment exists ✓

$ uv run python -c "import sys; print(sys.prefix)"
/Users/jangwonlee/Projects/heimdex/.venv  # Using virtual environment ✓
```

## Files Modified

### Fixed for Local Development

1. **Makefile** ✅
   - Added `uv venv` creation
   - Fixed install paths (from project root)
   - Added tool installation before use
   - All commands use `uv run`

2. **scripts/setup-dev.sh** ✅
   - Added virtual environment creation
   - Fixed install paths (from project root)
   - Uses `uv run` for pre-commit install

3. **scripts/run-tests.sh** ✅
   - Uses `uv run pytest`

### Already Correct (No Changes)

1. **apps/api/Dockerfile** ✅
   - Uses `uv pip install --system`

2. **apps/worker/Dockerfile** ✅
   - Uses `uv pip install --system`

3. **.github/workflows/ci.yml** ✅
   - Uses `uv pip install --system`

## Key Learnings

### 1. UV Requires Explicit venv Creation

Unlike pip which works with implicit environments, UV needs:

```bash
uv venv  # Create virtual environment first
uv pip install ...  # Then install packages
```

### 2. Path Context Matters

```bash
# WRONG - loses project context
cd subdir && uv pip install -e .

# RIGHT - maintains project context
uv pip install -e subdir
```

### 3. uv run vs Direct Execution

```bash
# Local (virtual environment)
uv run pytest  # Runs in virtual environment

# Docker/CI (system Python)
pytest  # Runs directly
```

## Testing Checklist

- [x] Virtual environment created automatically
- [x] All packages install successfully
- [x] Local dependencies (heimdex-common) resolve correctly
- [x] Lint command works with uv run
- [x] Test command works with uv run
- [x] Migration commands work with uv run
- [x] Docker builds still use --system
- [x] CI workflow still uses --system

## Next Steps

Everything is now working correctly! You can:

```bash
# Start fresh
make clean
make setup

# Develop
make lint
make test
make migrate

# Deploy
make build  # Uses --system in Docker
docker compose up
```

---

**Status:** ✅ FIXED
**Date:** 2025-11-01
**UV Version:** Latest
**Python:** 3.11.13
