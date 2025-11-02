# UV Setup - Complete and Working ✅

## Final Status: WORKING

All UV integration issues have been resolved. Local development uses virtual environments, containers use system-wide installation.

## What Was Fixed

### Issue 1: Virtual Environment Not Created

**Problem:** UV requires explicit virtual environment creation
**Fix:** Added `uv venv` command before installation

```makefile
install:
    @test -d .venv || $(UV) venv  # Create if doesn't exist
```

### Issue 2: Path Resolution Broken

**Problem:** Installing from subdirectories broke local package dependencies
**Fix:** Install from project root with relative paths

```makefile
# Before (BROKEN)
install:
    @cd packages/common && uv pip install -e ".[test]"  # Wrong!
    @cd apps/api && uv pip install -e .  # Can't find heimdex-common!

# After (FIXED)
install:
    @uv pip install -e "packages/common[test]"  # From root
    @uv pip install -e "apps/api"               # Can find heimdex-common ✓
```

### Issue 3: Pre-commit Not Installed

**Problem:** Trying to run `uv run pre-commit` before installing it
**Fix:** Install pre-commit before running it

```makefile
setup:
    @$(MAKE) install
    @$(UV) pip install pre-commit      # Install first
    @$(UV) run pre-commit install      # Then run
```

## Verification Results

### ✅ Setup Works

```bash
$ make setup
Installing uv package manager... ✓
Creating virtual environment... ✓
Installing dependencies... ✓
Installing pre-commit... ✓
Installing pre-commit hooks... ✓
✓ Development environment ready!
```

### ✅ Virtual Environment Created

```bash
$ ls .venv/
bin/  include/  lib/  pyvenv.cfg  ✓
```

### ✅ Packages Installed

```bash
$ uv run python -c "import heimdex_common"
# Works! ✓
```

### ✅ Imports Work

```bash
$ uv run python -c "import sys; print(sys.prefix)"
/Users/jangwonlee/Projects/heimdex/.venv  ✓
```

### ✅ Tools Work

```bash
$ make lint
Running ruff linter... ✓
Found 6 linting issues (expected)
```

## Complete Working Configuration

### Makefile (Local Development)

```makefile
# Virtual environment
install:
    @test -d .venv || uv venv
    @uv pip install -e "packages/common[test]"
    @uv pip install -e "apps/api"
    @uv pip install -e "apps/worker"

# Tools
lint:
    @uv pip install ruff || true
    @uv run ruff check .

# Tests
test-unit:
    @cd packages/common && uv run pytest tests/

# Migrations
migrate:
    @cd packages/common && uv run alembic upgrade head
```

### Dockerfile (Containers)

```dockerfile
# System-wide installation (no virtual environment)
RUN pip install --no-cache-dir uv
RUN uv pip install --system --no-cache --quiet .

# Direct execution (no uv run)
CMD ["uvicorn", "app.main:app"]
```

### CI Workflow

```yaml
# System-wide installation (no virtual environment)
- run: |
    curl -LsSf https://astral.sh/uv/install.sh | sh
    uv pip install --system -e ".[test]"

# Direct execution (no uv run)
- run: pytest tests/
```

## Environment Comparison

| Aspect | Local | Docker | CI |
|--------|-------|--------|-----|
| **Create venv?** | Yes (`uv venv`) | No | No |
| **Install flag** | (none) | `--system` | `--system` |
| **Run commands** | `uv run <cmd>` | `<cmd>` | `<cmd>` |
| **Example install** | `uv pip install -e .` | `uv pip install --system .` | `uv pip install --system .` |
| **Example run** | `uv run pytest` | `pytest` | `pytest` |

## Usage Guide

### Initial Setup

```bash
# One command to set everything up
make setup

# What it does:
# 1. Installs UV if needed
# 2. Creates virtual environment (.venv)
# 3. Installs all packages (common, api, worker)
# 4. Installs pre-commit
# 5. Configures pre-commit hooks
```

### Daily Development

```bash
# All these use the virtual environment automatically:
make install    # Install/update dependencies
make lint       # Run linting
make fmt        # Format code
make typecheck  # Type checking
make test       # Run tests
make migrate    # Run migrations

# Or run commands directly:
uv run pytest tests/
uv run ruff check .
uv run alembic upgrade head
```

### Docker Development

```bash
# Build images (uses --system inside)
make build

# Run services
make up

# Inside container, no virtual environment:
docker compose exec api python -c "import sys; print(sys.prefix)"
# Output: /usr/local (system Python)
```

### CI/CD

```bash
# Automatic on push
git push origin feature-branch

# CI workflow:
# 1. Installs UV
# 2. Installs packages with --system
# 3. Runs tests directly (no uv run)
```

## Files Modified

### ✅ Fixed Files

1. **Makefile**
   - Added virtual environment creation
   - Fixed installation paths (from project root)
   - Added pre-commit installation
   - All commands use `uv run`

2. **scripts/setup-dev.sh**
   - Added virtual environment creation
   - Fixed installation paths
   - Added pre-commit installation

3. **scripts/run-tests.sh**
   - Uses `uv run pytest`

### ✅ Already Correct (No Changes)

1. **apps/api/Dockerfile** - Uses `uv pip install --system`
2. **apps/worker/Dockerfile** - Uses `uv pip install --system`
3. **.github/workflows/ci.yml** - Uses `uv pip install --system`

## Troubleshooting

### Issue: "No virtual environment found"

**Solution:** Run `make setup` or `make install`

### Issue: "Package not found" when running tests

**Solution:** Use `uv run pytest` instead of `pytest` directly

### Issue: "Module not found" error

**Solution:** Reinstall from project root:

```bash
make clean
make install
```

### Issue: Pre-commit fails

**Solution:** Reinstall pre-commit:

```bash
uv pip install pre-commit
uv run pre-commit install
```

## Quick Reference

### Common Commands

| Task | Command | Environment |
|------|---------|-------------|
| Setup everything | `make setup` | Creates .venv |
| Install packages | `make install` | Uses .venv |
| Run linter | `make lint` | Uses .venv |
| Run tests | `make test` | Uses .venv |
| Run migrations | `make migrate` | Uses .venv |
| Build Docker | `make build` | Uses --system |
| Clean up | `make clean` | Removes .venv |

### Direct UV Commands

```bash
# Create virtual environment
uv venv

# Install package
uv pip install -e "packages/common[test]"

# Run command in virtual environment
uv run pytest tests/

# Run Python in virtual environment
uv run python script.py

# Check installed packages
uv pip list
```

## Success Checklist

- [x] Virtual environment created (.venv)
- [x] All packages install successfully
- [x] Local dependencies resolve (heimdex-common)
- [x] Pre-commit hooks installed
- [x] Lint command works
- [x] Test command works
- [x] Migration commands work
- [x] Docker still uses --system
- [x] CI still uses --system
- [x] All commands use virtual environment locally

## Next Steps

You're all set! You can now:

```bash
# Start developing
make lint
make test

# Make changes and commit (pre-commit runs automatically)
git add .
git commit -m "feat: my changes"

# Push to trigger CI
git push

# Deploy
make build
docker compose up
```

---

**Status:** ✅ COMPLETE AND WORKING
**Date:** 2025-11-01
**UV Version:** Latest
**Python:** 3.11.13
**Virtual Environment:** .venv (created and working)
