#!/usr/bin/env bash
#
# Validate Heimdex configuration files
# Checks .env, docker-compose.yml, and other config files
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "═══════════════════════════════════════════════════════════"
echo "  Heimdex Configuration Validation"
echo "═══════════════════════════════════════════════════════════"
echo ""

ERRORS=0

# Check .env file
echo "→ Checking deploy/.env..."
if [ ! -f "${PROJECT_ROOT}/deploy/.env" ]; then
    echo "  ❌ deploy/.env not found"
    echo "     Run 'cp deploy/.env.example deploy/.env' to create it"
    ERRORS=$((ERRORS + 1))
else
    # Check required environment variables
    REQUIRED_VARS=(
        "PGUSER"
        "PGPASSWORD"
        "PGDATABASE"
        "REDIS_URL"
        "QDRANT_URL"
        "VECTOR_SIZE"
        "EMBEDDING_BACKEND"
        "EMBEDDING_MODEL_NAME"
    )

    for var in "${REQUIRED_VARS[@]}"; do
        if ! grep -q "^${var}=" "${PROJECT_ROOT}/deploy/.env"; then
            echo "  ❌ Missing required variable: ${var}"
            ERRORS=$((ERRORS + 1))
        fi
    done

    if [ ${ERRORS} -eq 0 ]; then
        echo "  ✓ deploy/.env is valid"
    fi
fi
echo ""

# Check docker-compose.yml
echo "→ Checking deploy/docker-compose.yml..."
if [ ! -f "${PROJECT_ROOT}/deploy/docker-compose.yml" ]; then
    echo "  ❌ deploy/docker-compose.yml not found"
    ERRORS=$((ERRORS + 1))
else
    # Validate YAML syntax
    if command -v docker &> /dev/null; then
        if docker compose -f "${PROJECT_ROOT}/deploy/docker-compose.yml" config >/dev/null 2>&1; then
            echo "  ✓ docker-compose.yml is valid"
        else
            echo "  ❌ docker-compose.yml has syntax errors"
            ERRORS=$((ERRORS + 1))
        fi
    else
        echo "  ⚠️  Docker not available, skipping validation"
    fi
fi
echo ""

# Check pyproject.toml files
echo "→ Checking pyproject.toml files..."
for toml_file in \
    "${PROJECT_ROOT}/packages/common/pyproject.toml" \
    "${PROJECT_ROOT}/apps/api/pyproject.toml" \
    "${PROJECT_ROOT}/apps/worker/pyproject.toml"; do

    if [ ! -f "${toml_file}" ]; then
        echo "  ❌ Missing: ${toml_file}"
        ERRORS=$((ERRORS + 1))
    else
        echo "  ✓ Found: $(basename "$(dirname "${toml_file}")")/pyproject.toml"
    fi
done
echo ""

# Check Dockerfile files
echo "→ Checking Dockerfile files..."
for dockerfile in \
    "${PROJECT_ROOT}/apps/api/Dockerfile" \
    "${PROJECT_ROOT}/apps/worker/Dockerfile"; do

    if [ ! -f "${dockerfile}" ]; then
        echo "  ❌ Missing: ${dockerfile}"
        ERRORS=$((ERRORS + 1))
    else
        echo "  ✓ Found: $(basename "$(dirname "${dockerfile}")")/Dockerfile"
    fi
done
echo ""

# Summary
echo "═══════════════════════════════════════════════════════════"
if [ ${ERRORS} -eq 0 ]; then
    echo "  ✅ All configuration files are valid!"
    echo "═══════════════════════════════════════════════════════════"
    exit 0
else
    echo "  ❌ Found ${ERRORS} configuration error(s)"
    echo "═══════════════════════════════════════════════════════════"
    exit 1
fi
