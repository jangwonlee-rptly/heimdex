"""
Heimdex API Service Package.

This `__init__.py` file marks the `heimdex_api` directory as a Python package.
It serves as the main entry point for the package, defining essential metadata
that is used throughout the application for identification, logging, and
monitoring purposes.

Key Responsibilities of this Module:
- **Package Initialization**: Its presence allows the directory to be treated as
  a single, importable package.
- **Service Identification**: It defines `SERVICE_NAME`, a constant that uniquely
  identifies this service in a distributed environment. This is crucial for
  consolidated logging and metrics, where logs from multiple services might be
  aggregated.
- **Version Management**: It dynamically retrieves the package version from the
  installed package metadata (set in `pyproject.toml`). This ensures that the
  application always reports its correct version, which is vital for debugging,
  deployment verification, and cache busting in client applications. A fallback
  version is provided for local development environments where the package may
  not be formally installed.
"""

from importlib import metadata
from typing import Final

# SERVICE_NAME is a constant that provides a canonical name for this service.
# Using a constant avoids the use of "magic strings" for the service name
# throughout the codebase.
SERVICE_NAME: Final[str] = "api"

try:
    # Attempt to get the version from the installed package's metadata.
    # This is the standard way to manage versions for installable Python packages
    # and ensures that the version is consistent with the `pyproject.toml`.
    __version__ = metadata.version("heimdex-api")
except metadata.PackageNotFoundError:  # pragma: no cover
    # If the package is not installed (e.g., when running directly from source
    # in a local development environment), fall back to a default version.
    __version__ = "0.0.0"

# The `__all__` list defines the public API of this module. When a client
# does `from heimdex_api import *`, only these names will be imported.
__all__ = ["SERVICE_NAME", "__version__"]
