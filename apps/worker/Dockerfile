FROM python:3.11-slim

# Security: Run as non-root user
ENV PYTHONUNBUFFERED=1

# Install system dependencies (ffmpeg for future video processing)
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ffmpeg \
    && pip install --no-cache-dir uv \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /tmp \
    && chmod 1777 /tmp

WORKDIR /app

# Copy common package first
COPY --chown=appuser:appuser packages/common /app/packages/common

# Copy worker app
COPY --chown=appuser:appuser apps/worker/pyproject.toml ./
COPY --chown=appuser:appuser apps/worker/src ./src

# Install dependencies as root (for system-wide install)
RUN uv pip install --system --no-cache --quiet /app/packages/common && \
    uv pip install --system --no-cache --quiet .

# Pre-download default embedding model for deterministic builds
# This bakes the model weights into the image, ensuring fast startup and reproducibility
# The model cache directory is set via SENTENCE_TRANSFORMERS_HOME
ENV SENTENCE_TRANSFORMERS_HOME=/app/.cache/sentence-transformers
RUN mkdir -p $SENTENCE_TRANSFORMERS_HOME && \
    python3 -c "from sentence_transformers import SentenceTransformer; \
    print('Pre-downloading default embedding model...'); \
    model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2', device='cpu'); \
    print(f'Model loaded: dim={model.get_sentence_embedding_dimension()}');" && \
    chown -R appuser:appuser $SENTENCE_TRANSFORMERS_HOME

# Create writable tmp directory for read-only root filesystem
# Switch to non-root user
USER appuser

# Run Dramatiq worker with system Python (no uv run)
# Include both tasks and embeddings modules for actor discovery
CMD ["dramatiq", "heimdex_worker.tasks", "heimdex_worker.embeddings", "--processes", "1", "--threads", "2"]
