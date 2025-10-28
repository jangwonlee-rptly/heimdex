"""Heimdex worker service package."""

from importlib import metadata
from typing import Final

SERVICE_NAME: Final[str] = "worker"

try:
    __version__ = metadata.version("heimdex-worker")
except metadata.PackageNotFoundError:  # pragma: no cover - local execution only
    __version__ = "0.0.0"

__all__ = ["SERVICE_NAME", "__version__"]
