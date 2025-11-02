#!/usr/bin/env bash
#
# Setup development environment for Heimdex
# This script installs all dependencies and sets up pre-commit hooks
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "═══════════════════════════════════════════════════════════"
echo "  Heimdex Development Environment Setup"
echo "═══════════════════════════════════════════════════════════"
echo ""

# Check Python version
echo "→ Checking Python version..."
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)

if ! python3 -c "import sys; exit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
    echo "❌ Python 3.11+ is required. Found: ${PYTHON_VERSION}"
    exit 1
fi
echo "✓ Python ${PYTHON_VERSION} detected"
echo ""

# Install uv if not present
echo "→ Checking for uv package manager..."
if ! command -v uv &> /dev/null; then
    echo "  Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
fi
echo "✓ uv is available"
echo ""

# Create virtual environment if it doesn't exist
echo "→ Creating virtual environment..."
cd "${PROJECT_ROOT}"
if [ ! -d ".venv" ]; then
    uv venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi
echo ""

# Install Python dependencies (in virtual environment)
echo "→ Installing Python dependencies (in virtual environment)..."

echo "  Installing packages/common..."
uv pip install -e "packages/common[test]"

echo "  Installing apps/api..."
uv pip install -e "apps/api"

echo "  Installing apps/worker..."
uv pip install -e "apps/worker"

echo "✓ Dependencies installed in virtual environment"
echo ""

# Install pre-commit
echo "→ Installing pre-commit..."
cd "${PROJECT_ROOT}"
uv pip install pre-commit
echo "✓ Pre-commit installed"
echo ""

echo "→ Setting up pre-commit hooks..."
uv run pre-commit install
echo "✓ Pre-commit hooks installed"
echo ""

# Create .env if it doesn't exist
if [ ! -f "${PROJECT_ROOT}/deploy/.env" ]; then
    echo "→ Creating deploy/.env from .env.example..."
    if [ -f "${PROJECT_ROOT}/deploy/.env.example" ]; then
        cp "${PROJECT_ROOT}/deploy/.env.example" "${PROJECT_ROOT}/deploy/.env"
        echo "✓ Created deploy/.env"
        echo "  ⚠️  Please review and update deploy/.env with your configuration"
    else
        echo "  ⚠️  No .env.example found, skipping..."
    fi
    echo ""
fi

echo "═══════════════════════════════════════════════════════════"
echo "  ✅ Development environment setup complete!"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "Next steps:"
echo "  1. Review deploy/.env and update configuration"
echo "  2. Run 'make up' to start services"
echo "  3. Run 'make migrate' to run database migrations"
echo "  4. Run 'make test' to verify everything works"
echo ""
