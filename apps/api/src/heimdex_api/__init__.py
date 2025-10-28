"""Heimdex API service package."""

from importlib import metadata
from typing import Final

SERVICE_NAME: Final[str] = "api"

try:
    __version__ = metadata.version("heimdex-api")
except metadata.PackageNotFoundError:  # pragma: no cover - local execution only
    __version__ = "0.0.0"

__all__ = ["SERVICE_NAME", "__version__"]
