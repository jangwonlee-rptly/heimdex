FROM python:3.11-slim

# Security: Run as non-root user
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && pip install --no-cache-dir uv \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /tmp \
    && chmod 1777 /tmp

WORKDIR /app

# Copy common package first
COPY --chown=appuser:appuser packages/common /app/packages/common

# Copy API app
COPY --chown=appuser:appuser apps/api/pyproject.toml ./
COPY --chown=appuser:appuser apps/api/src ./src

# Install dependencies as root (for system-wide install)
RUN uv pip install --system --no-cache --quiet /app/packages/common && \
    uv pip install --system --no-cache --quiet .

# Switch to non-root user
USER appuser

# Cloud Run will set PORT env var; default to 8000 for local dev
ENV PORT=8000

# Use python -m for consistent execution (no uv run in containers)
CMD ["sh", "-c", "uvicorn heimdex_api.main:app --host 0.0.0.0 --port ${PORT}"]
