"""
Structured Logging Utilities for the Heimdex API Service.

This module provides a standardized way to emit structured JSON logs. Using
JSON logs allows for easier parsing, filtering, and analysis by logging
platforms (e.g., Datadog, Splunk).

The `log_event` function is the primary entrypoint, which automatically
enriches log records with service-wide context such as the service name,
environment, and version.
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
    Normalizes a log level to a valid, uppercase string.

    This function ensures that the provided log level is one of the recognized
    levels (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`). If the level is
    not valid, it defaults to `INFO` to prevent invalid log entries.

    Args:
        level (str): The log level string to normalize.

    Returns:
        str: The normalized, uppercase log level.
    """
    level_upper = level.upper()
    if level_upper not in _VALID_LEVELS:
        return "INFO"
    return level_upper


def log_event(level: str, msg: str, **fields: Any) -> None:
    """
    Emits a structured, single-line JSON log entry to standard output.

    This is the primary logging function for the service. It constructs a JSON
    log record containing a timestamp, service context, log level, a primary
    message, and any additional structured fields provided as keyword arguments.

    The log record is automatically enriched with the following fields:
    -   `ts`: The ISO 8601 timestamp in UTC.
    -   `service`: The name of the service (e.g., "api").
    -   `env`: The deployment environment (e.g., "local", "prod").
    -   `version`: The version of the service.
    -   `level`: The normalized log level.
    -   `msg`: The primary log message.

    Args:
        level (str): The severity level of the log (e.g., "INFO", "ERROR").
            This will be normalized to a valid level.
        msg (str): The primary, human-readable log message.
        **fields (Any): Arbitrary keyword arguments that will be included as
            structured fields in the JSON log entry. This is useful for
            adding context to the log, such as `job_id` or `duration_ms`.
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
