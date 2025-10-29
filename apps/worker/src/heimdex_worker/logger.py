"""
Structured Logging Utilities for the Heimdex Worker Service.

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
    Normalize a log level to a valid, uppercase string.

    If the provided level is not one of the recognized log levels, it defaults
    to "INFO".

    Args:
        level: The log level string to normalize.

    Returns:
        The normalized, uppercase log level.
    """
    level_upper = level.upper()
    if level_upper not in _VALID_LEVELS:
        return "INFO"
    return level_upper


def log_event(level: str, msg: str, **fields: Any) -> None:
    """
    Emit a structured, single-line JSON log entry.

    This function constructs a JSON log record containing a timestamp, service
    information, log level, message, and any additional structured fields.

    Args:
        level: The severity level of the log (e.g., "INFO", "ERROR").
        msg: The primary log message.
        **fields: Arbitrary keyword arguments to be included as structured
                  fields in the log entry.
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
