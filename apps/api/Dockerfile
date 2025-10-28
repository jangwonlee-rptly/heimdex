FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

RUN useradd --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app

# Copy common package first
COPY --chown=appuser:appuser packages/common /app/packages/common

# Copy API app
COPY --chown=appuser:appuser apps/api/pyproject.toml ./
COPY --chown=appuser:appuser apps/api/src ./src

# Install common package first, then API
RUN uv pip install --system --no-cache --quiet /app/packages/common && \
    uv pip install --system --no-cache --quiet .

USER appuser

CMD ["uvicorn", "heimdex_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
