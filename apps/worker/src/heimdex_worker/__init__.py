"""
Heimdex Worker Service Package.

This package contains the main entrypoint and core components for the Heimdex
background worker. It is responsible for processing asynchronous jobs from the
message queue.

Attributes:
    SERVICE_NAME (str): The name of the service, used for logging and identification.
    __version__ (str): The version of the service, retrieved from package metadata.
"""

from importlib import metadata
from typing import Final

SERVICE_NAME: Final[str] = "worker"

try:
    __version__ = metadata.version("heimdex-worker")
except metadata.PackageNotFoundError:  # pragma: no cover - local execution only
    __version__ = "0.0.0"

__all__ = ["SERVICE_NAME", "__version__"]
