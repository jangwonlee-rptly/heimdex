#!/usr/bin/env bash
#
# Wait for all Heimdex services to be ready
# Used in CI and local testing
#

set -euo pipefail

TIMEOUT="${TIMEOUT:-60}"
PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-heimdex}"
REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"
QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
API_URL="${API_URL:-http://localhost:8000}"

echo "Waiting for services to be ready (timeout: ${TIMEOUT}s)..."
echo ""

# Wait for PostgreSQL
echo "→ Waiting for PostgreSQL at ${PGHOST}:${PGPORT}..."
if timeout "${TIMEOUT}" bash -c "
    while ! pg_isready -h \"${PGHOST}\" -p \"${PGPORT}\" -U \"${PGUSER}\" 2>/dev/null; do
        sleep 1
    done
"; then
    echo "✓ PostgreSQL is ready"
else
    echo "❌ PostgreSQL timeout"
    exit 1
fi

# Wait for Redis
echo "→ Waiting for Redis at ${REDIS_HOST}:${REDIS_PORT}..."
if timeout "${TIMEOUT}" bash -c "
    while ! redis-cli -h \"${REDIS_HOST}\" -p \"${REDIS_PORT}\" ping 2>/dev/null | grep -q PONG; do
        sleep 1
    done
"; then
    echo "✓ Redis is ready"
else
    echo "❌ Redis timeout"
    exit 1
fi

# Wait for Qdrant
echo "→ Waiting for Qdrant at ${QDRANT_URL}..."
if timeout "${TIMEOUT}" bash -c "
    while ! curl -fsS \"${QDRANT_URL}/healthz\" >/dev/null 2>&1; do
        sleep 1
    done
"; then
    echo "✓ Qdrant is ready"
else
    echo "❌ Qdrant timeout"
    exit 1
fi

# Wait for API (optional)
if [ "${WAIT_FOR_API:-}" = "true" ]; then
    echo "→ Waiting for API at ${API_URL}..."
    if timeout "${TIMEOUT}" bash -c "
        while ! curl -fsS \"${API_URL}/healthz\" >/dev/null 2>&1; do
            sleep 1
        done
    "; then
        echo "✓ API is ready"
    else
        echo "❌ API timeout"
        exit 1
    fi
fi

echo ""
echo "✅ All services are ready!"
