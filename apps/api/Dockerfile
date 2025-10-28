FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

RUN useradd --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app

COPY --chown=appuser:appuser pyproject.toml ./
COPY --chown=appuser:appuser src ./src

RUN uv pip install --system --no-cache --quiet .

USER appuser

CMD ["uvicorn", "heimdex_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
