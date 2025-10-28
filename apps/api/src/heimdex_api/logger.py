"""Structured logging utilities for the Heimdex API service."""

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
    level_upper = level.upper()
    if level_upper not in _VALID_LEVELS:
        return "INFO"
    return level_upper


def log_event(level: str, msg: str, **fields: Any) -> None:
    """Emit a single-line JSON log entry."""

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
