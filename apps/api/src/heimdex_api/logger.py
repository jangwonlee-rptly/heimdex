"""
Structured JSON Logging Utilities for the Heimdex API Service.

This module provides a simple yet powerful utility for emitting structured logs in
a consistent JSON format. In a modern, distributed system, logs are not just for
human consumption; they are a critical source of machine-readable data for
monitoring, alerting, and analytics platforms (e.g., Datadog, Splunk, ELK Stack).

Why Structured JSON Logging?
- **Parsability**: JSON is a standard, unambiguous format that is easily parsed
  by virtually all log management tools. This eliminates the need for complex and
  brittle regex-based parsing of traditional log strings.
- **Search and Filtering**: When logs are structured with key-value pairs, it
  becomes trivial to search and filter them. For example, you can easily find
  all log entries for a specific `job_id` or all `ERROR` level logs with a
  certain `duration_ms`.
- **Automatic Enrichment**: This logger automatically enriches every log record
  with essential service context (`service` name, `env`, `version`), which is
  vital for distinguishing logs from different services in a centralized logging
  environment.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from typing import Any

from . import SERVICE_NAME, __version__

# The deployment environment, loaded from an environment variable.
_ENV = os.getenv("HEIMDEX_ENV", "local")
# A set of valid log levels to ensure that all log entries have a recognized severity.
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

    This is the primary logging function that should be used throughout the API
    service. It assembles a Python dictionary, populates it with standard,
    contextual fields and any custom fields, and then serializes it to a compact
    JSON string that is printed to stdout.

    Standard Fields Automatically Included:
    - `ts`: An ISO 8601 timestamp in UTC, providing a consistent timezone.
    - `service`: The name of this service ("api").
    - `env`: The deployment environment ("local", "prod", etc.).
    - `version`: The semantic version of the running service.
    - `level`: The normalized log severity.
    - `msg`: The primary, human-readable log message.

    Example Usage:
    ```python
    log_event(
        "INFO",
        "job_created",
        job_id="a-b-c-d",
        job_type="video_processing",
        user_id="user-123"
    )
    ```

    This would produce a JSON log similar to:
    ```json
    {"ts":"...", "service":"api", "env":"local", "version":"0.1.0", "level":"INFO",
     "msg":"job_created", "job_id":"a-b-c-d", "job_type":"video_processing",
     "user_id":"user-123"}
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
    # Add any custom fields provided by the caller.
    record.update(fields)
    # Use `separators` to create a compact JSON string, and `flush=True` to
    # ensure the log is written immediately, which is important in containerized
    # environments.
    print(json.dumps(record, separators=(",", ":")), file=sys.stdout, flush=True)
