# CI/CD Pipeline Documentation

This document describes the Continuous Integration and Continuous Deployment (CI/CD) infrastructure for the Heimdex project.

## Overview

The Heimdex CI/CD pipeline is designed to:

- **Ensure code quality** through automated linting, formatting, and type checking
- **Validate functionality** with comprehensive unit and integration tests
- **Enforce security** through secret scanning and infrastructure security checks
- **Maintain consistency** across development, CI, and production environments
- **Enable fast feedback** with parallelized jobs and intelligent caching

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Developer Workflow                      │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Local Development                                            │
│  ├─ make setup          → Install dependencies               │
│  ├─ make lint           → Run linters                        │
│  ├─ make fmt            → Format code                        │
│  ├─ make test           → Run all tests                      │
│  └─ git commit          → Trigger pre-commit hooks           │
│                                                               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     Pre-commit Hooks                         │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ✓ ruff (lint + format)  ✓ black               ✓ mypy       │
│  ✓ detect-secrets        ✓ yamllint            ✓ hadolint   │
│  ✓ actionlint            ✓ markdownlint        ✓ shellcheck │
│  ✓ terraform fmt/validate                                    │
│                                                               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    GitHub Actions CI                         │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Parallel Jobs:                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │ Lint & Format│  │  Unit Tests  │  │ Integration  │       │
│  │              │  │              │  │    Tests     │       │
│  │ • ruff       │  │ • pytest     │  │ • postgres   │       │
│  │ • black      │  │ • coverage   │  │ • redis      │       │
│  │ • mypy       │  │              │  │ • qdrant     │       │
│  └──────────────┘  └──────────────┘  │ • E2E tests  │       │
│                                       └──────────────┘       │
│  ┌────────────────────────────────┐                          │
│  │       Docker Build             │                          │
│  │  • Matrix: [api, worker]       │                          │
│  │  • Layer caching               │                          │
│  └────────────────────────────────┘                          │
│                                                               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  Infrastructure Validation                   │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  • Terraform fmt/validate                                     │
│  • Security scanning (tfsec, checkov)                         │
│  • OIDC scaffolding for future deployments                   │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## Components

### 1. Pre-commit Hooks (`.pre-commit-config.yaml`)

Enforces code quality standards before commits reach the repository.

**Configuration:**

- **Python 3.11** as the default language version
- **Pinned versions** for reproducibility
- **Comprehensive checks** covering all file types

**Hooks:**

| Hook | Purpose | Fail on Error |
|------|---------|---------------|
| ruff (lint) | Python linting | Yes |
| ruff-format | Python formatting | Yes |
| black | Python code formatting | Yes |
| mypy | Type checking | Yes |
| detect-secrets | Secret scanning | Yes |
| end-of-file-fixer | Fix EOF issues | Yes |
| trailing-whitespace | Remove trailing spaces | Yes |
| check-yaml | Validate YAML syntax | Yes |
| check-json | Validate JSON syntax | Yes |
| check-toml | Validate TOML syntax | Yes |
| yamllint | YAML linting | Yes |
| hadolint | Dockerfile linting | Yes |
| actionlint | GitHub Actions linting | Yes |
| markdownlint | Markdown linting | Yes |
| shellcheck | Shell script linting | Yes |
| terraform fmt | Terraform formatting | Yes |
| terraform validate | Terraform validation | Yes |

**Usage:**

```bash
# Install pre-commit hooks
pre-commit install

# Run manually on all files
pre-commit run --all-files

# Update hook versions
pre-commit autoupdate
```

### 2. CI Workflow (`.github/workflows/ci.yml`)

Main continuous integration pipeline that runs on every push and pull request.

**Triggers:**

- Push to `main` branch (excluding docs and infra changes)
- Pull requests to `main` branch (excluding docs and infra changes)
- Manual trigger via `workflow_dispatch`

**Jobs:**

#### Lint & Format (timeout: 10 minutes)

```yaml
Steps:
1. Checkout code
2. Set up Python 3.11
3. Install uv
4. Cache uv dependencies
5. Install dependencies
6. Run ruff (lint)
7. Run ruff (format check)
8. Run mypy (type check)
```

**Technologies:**

- UV package manager for fast dependency installation
- Ruff for linting and formatting
- MyPy for type checking

#### Unit Tests (timeout: 10 minutes)

```yaml
Steps:
1. Checkout code
2. Set up Python 3.11
3. Install uv
4. Cache uv dependencies
5. Install dependencies
6. Run pytest (excluding E2E tests)
7. Upload test results on failure
```

**Test Configuration:**

- Excludes `test_embeddings_e2e.py` (integration test)
- Short traceback format for readability
- Artifact upload on failure for debugging

#### Integration Tests (timeout: 20 minutes)

```yaml
Services:
- PostgreSQL 17 (with health checks)
- Redis 7 (with health checks)
- Qdrant v1.11.3 (with health checks)

Steps:
1. Checkout code
2. Set up Python 3.11
3. Install uv
4. Cache uv dependencies
5. Install all packages
6. Wait for services
7. Run database migrations
8. Start API server (background)
9. Start worker (background)
10. Run E2E tests
11. Upload logs on failure
```

**Environment Configuration:**

```bash
PGUSER=heimdex
PGPASSWORD=heimdex
PGDATABASE=heimdex
PGHOST=localhost
PGPORT=5432
REDIS_URL=redis://localhost:6379/0
QDRANT_URL=http://localhost:6333
VECTOR_SIZE=384
EMBEDDING_BACKEND=sentence
EMBEDDING_MODEL_NAME=minilm-l6-v2
EMBEDDING_DEVICE=cpu
EMBEDDING_VALIDATE_ON_STARTUP=false
```

#### Docker Build (timeout: 20 minutes)

```yaml
Strategy:
  Matrix: [api, worker]

Steps:
1. Checkout code
2. Set up Docker Buildx
3. Cache Docker layers
4. Build service image
5. Move cache for next run
```

**Optimizations:**

- Layer caching for faster builds
- Matrix parallelization for API and worker
- Cache rotation to avoid stale data

#### CI Summary

```yaml
Dependencies: [lint, unit-tests, integration-tests, docker-build]

Steps:
1. Check all job statuses
2. Report failures
3. Exit with appropriate code
```

**Success Criteria:**

- Lint must pass
- Unit tests must pass
- Integration tests must pass (or be expected to fail)
- Docker build must pass

### 3. Infrastructure Workflow (`.github/workflows/infra.yml`)

Validates Terraform infrastructure code without making actual changes.

**Triggers:**

- Manual trigger via `workflow_dispatch`
- Pull requests touching `deploy/infra/**`
- Push to `main` touching `deploy/infra/**`

**Jobs:**

#### Terraform Validation (timeout: 10 minutes)

```yaml
Permissions:
  id-token: write     # For OIDC (future use)
  contents: read      # For checkout
  pull-requests: write # For PR comments

Steps:
1. Checkout code
2. Setup Terraform 1.9.0
3. Cache Terraform plugins
4. Run terraform fmt -check -recursive
5. Run terraform init -backend=false
6. Run terraform validate
7. Run terraform plan (dry run)
8. Comment PR with results
9. Check all results
```

**Features:**

- Local backend (no state access)
- OIDC scaffolding for future WIF integration
- PR comments with validation results
- Dry-run plan without credentials

#### Security Scan (timeout: 10 minutes)

```yaml
Steps:
1. Checkout code
2. Run tfsec (soft fail)
3. Run checkov (soft fail)
```

**Security Tools:**

- **tfsec**: Terraform static analysis
- **checkov**: Infrastructure security scanning

**Note:** Security scans use `soft_fail: true` to show issues without blocking PRs.

#### Infrastructure Summary

```yaml
Dependencies: [terraform-validate, security-scan]

Steps:
1. Check job statuses
2. Report results
3. Exit with appropriate code
```

### 4. Makefile

Provides unified interface for CI operations and local development.

**Key Targets:**

| Target | Purpose | CI Usage |
|--------|---------|----------|
| `help` | Show all available targets | Documentation |
| `setup` | Install uv + dependencies + hooks | Initial setup |
| `install` | Install Python dependencies | CI: before tests |
| `lint` | Run ruff linting | CI: lint job |
| `fmt` | Format code | Local dev |
| `typecheck` | Run mypy | CI: lint job |
| `pre-commit` | Run all pre-commit hooks | Local validation |
| `test` | Run all tests | Full test suite |
| `test-unit` | Run unit tests only | CI: unit-tests job |
| `test-integration` | Run integration tests only | CI: integration-tests job |
| `build` | Build Docker images | CI: docker-build job |
| `up` | Start services | Local dev |
| `down` | Stop services | Local dev |
| `migrate` | Run database migrations | CI: before integration tests |
| `clean` | Remove build artifacts | Cleanup |

**Example CI Equivalents:**

```bash
# What CI does in the lint job:
make lint
make typecheck

# What CI does in the unit-tests job:
make test-unit

# What CI does in the integration-tests job:
make up
make migrate
make test-integration

# What CI does in the docker-build job:
make build
```

### 5. Helper Scripts (`scripts/`)

Reusable bash scripts used by both CI and local development.

#### `setup-dev.sh`

**Purpose:** One-command development environment setup

**What it does:**

- Validates Python 3.11+ is installed
- Installs uv if not present
- Installs all Python dependencies
- Sets up pre-commit hooks
- Creates `.env` from `.env.example`

**Usage:**

```bash
./scripts/setup-dev.sh
```

**CI Usage:** Not used in CI (CI installs dependencies directly)

#### `wait-for-services.sh`

**Purpose:** Wait for all services to be healthy

**What it does:**

- Waits for PostgreSQL (with `pg_isready`)
- Waits for Redis (with `redis-cli ping`)
- Waits for Qdrant (with health endpoint)
- Optionally waits for API (with health endpoint)

**Usage:**

```bash
# Wait for data services only
./scripts/wait-for-services.sh

# Wait for data services + API
WAIT_FOR_API=true ./scripts/wait-for-services.sh
```

**CI Usage:**

```yaml
- name: Wait for services
  run: |
    timeout 30 bash -c 'until pg_isready ...; do sleep 1; done'
    timeout 30 bash -c 'until redis-cli ping ...; do sleep 1; done'
    timeout 30 bash -c 'until wget qdrant/healthz ...; do sleep 1; done'
```

#### `run-tests.sh`

**Purpose:** Run tests with proper validation

**What it does:**

- Validates environment is ready
- Runs requested test suite
- Provides clear success/failure output

**Usage:**

```bash
# Run all tests
./scripts/run-tests.sh all

# Run only unit tests
./scripts/run-tests.sh unit

# Run only integration tests
./scripts/run-tests.sh integration
```

**CI Usage:** Not used directly (CI runs pytest directly for better control)

#### `validate-config.sh`

**Purpose:** Validate all configuration files

**What it does:**

- Checks `.env` exists and has required variables
- Validates `docker-compose.yml` syntax
- Checks for required `pyproject.toml` files
- Checks for required Dockerfiles

**Usage:**

```bash
./scripts/validate-config.sh
```

**CI Usage:** Could be added as a pre-flight check in CI

## Performance Characteristics

### Target Times

| Job | Target | Typical |
|-----|--------|---------|
| Lint & Format | < 5 min | ~2-3 min |
| Unit Tests | < 5 min | ~2-3 min |
| Integration Tests | < 20 min | ~10-15 min |
| Docker Build (each) | < 20 min | ~5-10 min |
| **Total Pipeline** | **< 25 min** | **~15-20 min** |

### Optimization Strategies

1. **Dependency Caching**
   - UV dependencies cached by `pyproject.toml` hash
   - Docker layer caching for builds
   - Terraform plugin caching

2. **Parallelization**
   - Lint, unit tests, integration tests run in parallel
   - Docker builds run in parallel via matrix

3. **Early Termination**
   - Concurrency groups cancel redundant runs
   - Fast-fail on critical errors

4. **Service Optimization**
   - Alpine-based images for faster startup
   - Health checks to avoid premature test runs
   - Shared service definitions

## Local Development Workflow

### Initial Setup

```bash
# Clone repository
git clone https://github.com/your-org/heimdex.git
cd heimdex

# Run setup script
./scripts/setup-dev.sh

# Or use Makefile
make setup
```

### Daily Workflow

```bash
# Start services
make up

# Run migrations
make migrate

# Make changes to code
vim packages/common/src/...

# Run tests locally
make test-unit

# Format code
make fmt

# Run linters
make lint

# Run type checker
make typecheck

# Or run all pre-commit hooks
make pre-commit

# Commit changes (pre-commit runs automatically)
git add .
git commit -m "feat: add new feature"

# Push to GitHub (CI runs automatically)
git push origin feature-branch
```

### Testing

```bash
# Run all tests (unit + integration)
make test

# Run only unit tests (fast)
make test-unit

# Run only integration tests (requires services)
make test-integration

# Or use helper script
./scripts/run-tests.sh unit
```

### Troubleshooting

```bash
# Check service health
make health
make readyz

# View service logs
make logs

# Reset all data
make reset

# Validate configuration
./scripts/validate-config.sh

# Clean build artifacts
make clean
```

## CI/CD Best Practices

### For Developers

1. **Always run pre-commit locally** before pushing

   ```bash
   pre-commit run --all-files
   ```

2. **Test locally before pushing**

   ```bash
   make test
   ```

3. **Keep CI green** - fix failures immediately

4. **Review CI logs** when tests fail

5. **Use draft PRs** for work-in-progress

### For Maintainers

1. **Monitor CI performance** - ensure jobs stay under target times

2. **Update dependencies regularly**

   ```bash
   pre-commit autoupdate
   ```

3. **Keep Docker images lean** - minimize layer sizes

4. **Review failed jobs** - identify flaky tests

5. **Update documentation** when changing CI

## Security Considerations

### Secret Management

- **Never commit secrets** - `detect-secrets` hook catches most cases
- **Use GitHub Secrets** for sensitive values in CI
- **Use OIDC/WIF** for cloud authentication (scaffolded, not active)
- **Rotate secrets regularly** - especially dev/test secrets

### Access Control

- **CI has minimal permissions** - only what's needed
- **OIDC token** available but not used yet
- **PR comments** require write permission (granted)

### Dependency Security

- **Pre-commit hooks** scan for known issues
- **Terraform security** scanned with tfsec and checkov
- **Docker images** use official base images
- **Pin versions** for reproducibility

## Troubleshooting

### Common Issues

#### Pre-commit hooks fail

**Symptom:** `pre-commit run --all-files` shows errors

**Solution:**

```bash
# Auto-fix formatting issues
make fmt

# Check remaining issues
make lint

# Fix type errors manually
# Then retry
pre-commit run --all-files
```

#### CI lint job fails but local pre-commit passes

**Symptom:** GitHub Actions lint job fails, but `pre-commit run --all-files` passes locally

**Possible causes:**

- Different Python versions
- Stale local cache
- Unpinned dependency versions

**Solution:**

```bash
# Update pre-commit hooks
pre-commit autoupdate

# Clear caches
make clean

# Re-run checks
pre-commit run --all-files
```

#### Integration tests fail in CI but pass locally

**Symptom:** E2E tests fail in GitHub Actions but work with `make test-integration`

**Possible causes:**

- Service startup timing
- Port conflicts
- Missing environment variables

**Solution:**

1. Check CI logs for service health
2. Verify environment variables match
3. Add more wait time if needed
4. Check for race conditions

#### Docker build fails with layer cache

**Symptom:** Docker build fails with cache-related errors

**Solution:**

```bash
# Clear Docker cache
docker builder prune -af

# Rebuild without cache
docker compose build --no-cache
```

#### Terraform validation fails

**Symptom:** `terraform validate` fails in CI

**Solution:**

```bash
# Run terraform fmt locally
cd deploy/infra
terraform fmt -recursive

# Run terraform validate locally
terraform init -backend=false
terraform validate

# Commit fixes
git add .
git commit -m "fix: terraform formatting"
```

## Future Enhancements

### Planned Improvements

1. **Workload Identity Federation (WIF)**
   - OIDC scaffolding already in place
   - Will enable keyless authentication to GCP
   - Eliminates need for service account keys

2. **Test Coverage Reporting**
   - Add coverage thresholds
   - Upload coverage reports to Codecov
   - Block PRs below threshold

3. **Performance Regression Detection**
   - Track test execution times
   - Alert on significant slowdowns
   - Optimize slow tests

4. **Auto-merge for Dependabot**
   - Automatically merge dependency updates
   - If all tests pass
   - For patch and minor versions

5. **Deployment Pipeline**
   - Add staging environment
   - Add production deployment
   - Use WIF for authentication

## References

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [pre-commit Documentation](https://pre-commit.com/)
- [UV Package Manager](https://github.com/astral-sh/uv)
- [Ruff Linter](https://github.com/astral-sh/ruff)
- [Docker Buildx](https://docs.docker.com/buildx/working-with-buildx/)
- [Terraform](https://www.terraform.io/docs)

## Support

For CI/CD issues:

1. Check this documentation
2. Review GitHub Actions logs
3. Check pre-commit hook output
4. Open an issue with:
   - Full error message
   - Steps to reproduce
   - Local environment details
   - CI logs (if applicable)
