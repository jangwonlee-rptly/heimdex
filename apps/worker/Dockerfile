FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

RUN useradd --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app

COPY --chown=appuser:appuser pyproject.toml ./
COPY --chown=appuser:appuser src ./src

RUN uv pip install --system --no-cache --quiet .

USER appuser

CMD ["python", "-m", "heimdex_worker.main"]
