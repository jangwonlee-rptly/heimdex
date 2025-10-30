"""
Heimdex Worker Service Package.

This `__init__.py` file marks the `heimdex_worker` directory as a Python package.
It serves as the main entry point for the package, defining essential metadata
that is used throughout the worker for identification, logging, and monitoring.

Key Responsibilities of this Module:
- **Package Initialization**: Its presence allows the directory to be treated as
  a single, importable package.
- **Service Identification**: It defines `SERVICE_NAME`, a constant that uniquely
  identifies this service as the "worker". This is crucial for distinguishing
  its logs and metrics from those of other services like the "api".
- **Version Management**: It dynamically retrieves the package version from the
  installed package metadata (set in `pyproject.toml`). This ensures that the
  worker always reports its correct version, which is vital for deployment
  verification and for understanding which version of the code is processing
  jobs. A fallback version is provided for local development.
"""

from importlib import metadata
from typing import Final

# SERVICE_NAME provides a canonical, unambiguous name for this service.
SERVICE_NAME: Final[str] = "worker"

try:
    # Get the version from the installed package's metadata, ensuring
    # consistency with `pyproject.toml`.
    __version__ = metadata.version("heimdex-worker")
except metadata.PackageNotFoundError:  # pragma: no cover
    # Fallback for local development when the package is not formally installed.
    __version__ = "0.0.0"

# Define the public API of this module.
__all__ = ["SERVICE_NAME", "__version__"]
