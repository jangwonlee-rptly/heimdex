"""
Structured JSON Logging Utilities for the Heimdex Worker Service.

This module provides a standardized logging utility for the worker, ensuring that
all log output is in a machine-readable JSON format. This is especially critical
for a background worker, as its logs are the primary tool for observing its behavior,
debugging issues with job processing, and monitoring its health.

Why Structured JSON Logging for a Worker?
- **Traceability**: By including a `job_id` in every log message related to a
  specific job, it becomes possible to trace the entire execution of a single
  job across multiple log entries, even in a highly concurrent environment.
- **Error Analysis**: When a job fails, structured logs allow for precise
  analysis. You can filter for all logs with `level: "ERROR"` and a specific
  `actor_name` to quickly identify the root cause of failures.
- **Performance Monitoring**: Logging key metrics like `duration_ms` for different
  stages of a job allows for performance monitoring and the identification of
  bottlenecks in job processing.
- **Automatic Enrichment**: This logger automatically enriches every log with
  essential service context (`service: "worker"`, `env`, `version`), which is
  vital for distinguishing worker logs from API logs in a centralized system.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from typing import Any

from . import SERVICE_NAME, __version__

_ENV = os.getenv("HEIMDEX_ENV", "local")
_VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def _normalize_level(level: str) -> str:
    """
    Ensures that a log level is a valid, uppercase string.

    This helper function provides a layer of robustness by guaranteeing that
    the `level` field in the final JSON log is always one of the predefined,
    standard levels. If an invalid level is provided, it defaults to `INFO`.

    Args:
        level: The log level string to be normalized.

    Returns:
        The normalized, uppercase log level string.
    """
    level_upper = level.upper()
    return level_upper if level_upper in _VALID_LEVELS else "INFO"


def log_event(level: str, msg: str, **fields: Any) -> None:
    """
    Emits a structured, single-line JSON log entry to standard output.

    This is the primary logging function that should be used throughout the worker
    service. It assembles a Python dictionary, populates it with standard,
    contextual fields and any custom fields, and then serializes it to a compact
    JSON string that is printed to stdout.

    Standard Fields Automatically Included:
    - `ts`: An ISO 8601 timestamp in UTC.
    - `service`: The name of this service ("worker").
    - `env`: The deployment environment.
    - `version`: The semantic version of the running worker.
    - `level`: The normalized log severity.
    - `msg`: The primary, human-readable log message.

    Example Usage in a Worker Actor:
    ```python
    log_event(
        "INFO",
        "processing_stage_complete",
        job_id="a-b-c-d",
        actor_name="process_video",
        stage="transcoding",
        duration_ms=5123
    )
    ```

    Args:
        level: The severity level of the log (e.g., "INFO", "ERROR").
        msg: The primary, human-readable log message.
        **fields: Arbitrary keyword arguments that will be added as key-value
                  pairs to the root of the JSON log object.
    """
    record = {
        "ts": datetime.now(UTC).isoformat(),
        "service": SERVICE_NAME,
        "env": _ENV,
        "version": __version__,
        "level": _normalize_level(level),
        "msg": msg,
    }
    record.update(fields)
    print(json.dumps(record, separators=(",", ":")), file=sys.stdout, flush=True)
