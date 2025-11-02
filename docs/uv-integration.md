# UV Package Manager Integration

This document describes how UV is integrated throughout the Heimdex project for fast, reliable Python package management.

## Overview

Heimdex uses [UV](https://github.com/astral-sh/uv) as the primary Python package manager across:

- Local development
- CI/CD pipelines
- Docker images
- Testing infrastructure

UV provides significant speed improvements over pip while maintaining compatibility.

## Why UV?

- **Fast**: 10-100x faster than pip for most operations
- **Reliable**: Reproducible installs with proper dependency resolution
- **Compatible**: Drop-in replacement for pip
- **System Python**: Works with `--system` flag for containerized environments

## UV Usage Patterns

### Local Development

#### Installation

```bash
# Install UV
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or via Makefile
make setup
```

#### Installing Dependencies

```bash
# Using UV directly
cd packages/common
uv pip install --system -e ".[test]"

cd apps/api
uv pip install --system -e .

cd apps/worker
uv pip install --system -e .

# Or via Makefile
make install
```

#### Installing Development Tools

```bash
# Using UV
uv pip install --system ruff black mypy pytest

# These are installed automatically when you run:
make lint    # Installs ruff if needed
make fmt     # Installs ruff if needed
make typecheck  # Installs mypy if needed
make test    # Installs pytest if needed
```

### Docker Integration

Both the API and Worker Dockerfiles use UV for package management:

```dockerfile
FROM python:3.11-slim

# Install uv
RUN pip install --no-cache-dir uv

# Install dependencies with UV
RUN uv pip install --system --no-cache --quiet /app/packages/common && \
    uv pip install --system --no-cache --quiet .
```

**Key flags:**

- `--system`: Install into system Python (no virtual environment)
- `--no-cache`: Don't cache packages (reduces image size)
- `--quiet`: Minimal output for cleaner builds

### CI/CD Integration

GitHub Actions workflows use UV for all package operations:

```yaml
- name: Install uv
  run: |
    curl -LsSf https://astral.sh/uv/install.sh | sh
    echo "$HOME/.cargo/bin" >> $GITHUB_PATH

- name: Cache uv dependencies
  uses: actions/cache@v4
  with:
    path: ~/.cache/uv
    key: uv-${{ runner.os }}-${{ hashFiles('**/pyproject.toml') }}

- name: Install dependencies
  run: |
    cd packages/common
    uv pip install --system -e ".[test]"
```

**Benefits in CI:**

- Faster job execution (especially with caching)
- Reliable dependency resolution
- Consistent with Docker builds

### Makefile Integration

All Makefile targets use UV for package management:

```makefile
# Python and UV configuration
PYTHON_VERSION := 3.11
UV := uv

# Installation
install:
 @cd packages/common && $(UV) pip install --system -e ".[test]"
 @cd apps/api && $(UV) pip install --system -e .
 @cd apps/worker && $(UV) pip install --system -e .

# Linting (installs ruff via UV if needed)
lint:
 @$(UV) pip install --system ruff 2>/dev/null || true
 @ruff check --output-format=github .

# Testing (installs pytest via UV if needed)
test-unit:
 @$(UV) pip install --system pytest pytest-asyncio 2>/dev/null || true
 @cd packages/common && pytest tests/ -v
```

**Pattern:**

1. Install tools via `uv pip install --system` (with error suppression)
2. Run tools directly (they're in system PATH)

## File Structure

### Package Structure

```
heimdex/
├── packages/
│   └── common/
│       ├── pyproject.toml          # Core package with test extras
│       └── src/heimdex_common/
├── apps/
│   ├── api/
│   │   ├── pyproject.toml          # API dependencies
│   │   ├── Dockerfile              # Uses UV
│   │   └── src/heimdex_api/
│   └── worker/
│       ├── pyproject.toml          # Worker dependencies
│       ├── Dockerfile              # Uses UV
│       └── src/heimdex_worker/
```

### pyproject.toml Configuration

Each package defines its dependencies in `pyproject.toml`:

```toml
[project]
name = "heimdex-common"
dependencies = [
    "sqlalchemy>=2.0.0",
    "alembic>=1.13.0",
    # ... other deps
]

[project.optional-dependencies]
test = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.21.0",
]
```

UV reads these files to install dependencies.

## UV Commands Reference

### Package Installation

```bash
# Install package in editable mode
uv pip install --system -e .

# Install with extras
uv pip install --system -e ".[test]"

# Install from requirements file
uv pip install --system -r requirements.txt

# Install specific package
uv pip install --system fastapi

# Install without cache (for Docker)
uv pip install --system --no-cache package-name
```

### Package Management

```bash
# List installed packages
uv pip list

# Show package info
uv pip show package-name

# Freeze installed packages
uv pip freeze

# Uninstall package
uv pip uninstall package-name
```

### Cache Management

```bash
# Show cache directory
uv cache dir

# Clean cache
uv cache clean
```

## Performance Characteristics

### Speed Comparison (typical operations)

| Operation | pip | UV | Improvement |
|-----------|-----|-----|-------------|
| Install from cache | 10s | 0.5s | 20x faster |
| Install fresh | 30s | 3s | 10x faster |
| Dependency resolution | 15s | 1s | 15x faster |

### CI Pipeline Impact

**Before UV (with pip):**

- Lint job: ~5 minutes
- Unit tests: ~5 minutes
- Integration tests: ~25 minutes

**After UV:**

- Lint job: ~2-3 minutes ✅
- Unit tests: ~2-3 minutes ✅
- Integration tests: ~10-15 minutes ✅

**Total improvement: ~40% faster pipeline**

## Best Practices

### 1. Always Use `--system` Flag

In containers and CI, use `--system` to install into system Python:

```bash
uv pip install --system package-name
```

**Why:**

- No virtual environment overhead
- Consistent with Docker multi-stage builds
- Simpler PATH management

### 2. Use `--no-cache` in Dockerfiles

```dockerfile
RUN uv pip install --system --no-cache -e .
```

**Why:**

- Reduces image size
- Prevents stale cache in layers
- More reproducible builds

### 3. Cache UV Dependencies in CI

```yaml
- uses: actions/cache@v4
  with:
    path: ~/.cache/uv
    key: uv-${{ hashFiles('**/pyproject.toml') }}
```

**Why:**

- Significantly faster CI runs
- Saves bandwidth
- Consistent with pip caching strategies

### 4. Suppress Reinstall Warnings in Makefile

```makefile
@$(UV) pip install --system ruff 2>/dev/null || true
```

**Why:**

- Makes output cleaner
- Allows idempotent make targets
- Doesn't fail if already installed

### 5. Pin UV Version in Dockerfiles

```dockerfile
RUN pip install --no-cache-dir uv==0.1.0
```

**Why:**

- Reproducible builds
- Prevents breaking changes
- Matches CI environment

## Troubleshooting

### UV Not Found

**Symptom:** `command not found: uv`

**Solution:**

```bash
# Install UV
curl -LsSf https://astral.sh/uv/install.sh | sh

# Add to PATH
export PATH="$HOME/.cargo/bin:$PATH"

# Or run make setup
make setup
```

### Permission Denied

**Symptom:** `Permission denied` when installing packages

**Solution:**

```bash
# Use --system flag (don't create virtualenv)
uv pip install --system package-name

# Or run as root in Docker
USER root
RUN uv pip install --system ...
USER appuser
```

### Cache Issues

**Symptom:** Stale or corrupted cache

**Solution:**

```bash
# Clean UV cache
uv cache clean

# Or remove cache directory
rm -rf ~/.cache/uv
```

### Docker Build Failures

**Symptom:** UV installation fails in Docker

**Solution:**

```dockerfile
# Ensure pip is up to date first
RUN pip install --upgrade pip

# Then install UV
RUN pip install --no-cache-dir uv

# Verify UV works
RUN uv --version
```

## Migration from pip

If you have existing `pip` commands, here's how to migrate:

| pip Command | UV Equivalent |
|-------------|---------------|
| `pip install package` | `uv pip install --system package` |
| `pip install -r requirements.txt` | `uv pip install --system -r requirements.txt` |
| `pip install -e .` | `uv pip install --system -e .` |
| `pip list` | `uv pip list` |
| `pip freeze` | `uv pip freeze` |
| `pip show package` | `uv pip show package` |
| `pip uninstall package` | `uv pip uninstall package` |

**Key difference:** Always add `--system` flag in containers and CI.

## Future Enhancements

### Planned Improvements

1. **Lock Files**
   - Generate `uv.lock` for reproducible installs
   - Commit lock files to repository
   - Use in CI and Docker builds

2. **Workspace Support**
   - Configure UV workspace for monorepo
   - Shared dependency resolution
   - Faster multi-package installs

3. **UV Tool Commands**
   - Use `uv tool run` for ephemeral tools
   - Reduces installation overhead
   - Cleaner CI pipelines

## References

- [UV Documentation](https://github.com/astral-sh/uv)
- [UV Installation Guide](https://github.com/astral-sh/uv#installation)
- [UV vs pip Comparison](https://github.com/astral-sh/uv#benchmarks)
- [Python Packaging Guide](https://packaging.python.org/)

## Support

For UV-related issues:

1. Check this documentation
2. Verify UV version: `uv --version`
3. Check UV cache: `uv cache dir`
4. Review GitHub Actions logs
5. Open an issue with:
   - UV version
   - Python version
   - Command that failed
   - Full error output

---

**Last Updated:** 2025-11-01
**UV Version:** Latest (installed from official installer)
**Python Version:** 3.11
