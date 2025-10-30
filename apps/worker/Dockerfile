FROM python:3.11-slim

# Security: Run as non-root user
ENV PYTHONUNBUFFERED=1

# Install system dependencies (ffmpeg for future video processing)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install uv for package management
RUN pip install --no-cache-dir uv

# Create non-root user with no shell access
RUN useradd --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app

# Copy common package first
COPY --chown=appuser:appuser packages/common /app/packages/common

# Copy worker app
COPY --chown=appuser:appuser apps/worker/pyproject.toml ./
COPY --chown=appuser:appuser apps/worker/src ./src

# Install dependencies as root (for system-wide install)
RUN uv pip install --system --no-cache --quiet /app/packages/common && \
    uv pip install --system --no-cache --quiet .

# Create writable tmp directory for read-only root filesystem
RUN mkdir -p /tmp && chmod 1777 /tmp

# Switch to non-root user
USER appuser

# Run Dramatiq worker with system Python (no uv run)
CMD ["dramatiq", "heimdex_worker.tasks", "--processes", "1", "--threads", "2"]
