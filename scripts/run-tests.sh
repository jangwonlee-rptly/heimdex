#!/usr/bin/env bash
#
# Run Heimdex tests with proper setup
# Supports: unit, integration, or all tests
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

TEST_TYPE="${1:-all}"

usage() {
    echo "Usage: $0 [unit|integration|all]"
    echo ""
    echo "Examples:"
    echo "  $0 unit         # Run unit tests only"
    echo "  $0 integration  # Run integration tests only"
    echo "  $0 all          # Run all tests (default)"
    exit 1
}

run_unit_tests() {
    echo "═══════════════════════════════════════════════════════════"
    echo "  Running Unit Tests"
    echo "═══════════════════════════════════════════════════════════"
    echo ""

    cd "${PROJECT_ROOT}/packages/common"
    uv run pytest tests/ -v --tb=short --ignore=tests/test_embeddings_e2e.py

    echo ""
    echo "✅ Unit tests passed!"
}

run_integration_tests() {
    echo "═══════════════════════════════════════════════════════════"
    echo "  Running Integration Tests"
    echo "═══════════════════════════════════════════════════════════"
    echo ""

    # Check if services are running
    echo "→ Checking if services are available..."
    if ! curl -fsS http://localhost:8000/healthz >/dev/null 2>&1; then
        echo "❌ API is not running. Start services with 'make up'"
        exit 1
    fi

    cd "${PROJECT_ROOT}/packages/common"
    uv run pytest tests/test_embeddings_e2e.py -v --tb=short

    echo ""
    echo "✅ Integration tests passed!"
}

case "${TEST_TYPE}" in
    unit)
        run_unit_tests
        ;;
    integration)
        run_integration_tests
        ;;
    all)
        run_unit_tests
        echo ""
        run_integration_tests
        ;;
    *)
        echo "❌ Invalid test type: ${TEST_TYPE}"
        echo ""
        usage
        ;;
esac

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  ✅ All tests completed successfully!"
echo "═══════════════════════════════════════════════════════════"
