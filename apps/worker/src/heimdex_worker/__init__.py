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
- **Startup Validation**: Performs fail-fast validation of embedding model
  configuration to catch dimension mismatches before processing any jobs.
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


# --- Startup Validation (Fail-Fast) ---
# This code runs when the worker module is imported, ensuring that configuration
# errors are caught immediately at startup rather than at job processing time.
def _validate_startup_configuration() -> None:
    """
    Validate critical configuration at worker startup.

    This function performs fail-fast validation of the embedding model configuration.
    If the adapter's dimension doesn't match VECTOR_SIZE, the worker will refuse to
    start, preventing silent data corruption or runtime failures.

    This validation respects the EMBEDDING_VALIDATE_ON_STARTUP environment variable
    (defaults to true). Set to false to bypass validation (not recommended for production).

    Raises:
        ValueError: If embedding dimension doesn't match VECTOR_SIZE
        ImportError: If required dependencies are missing
    """
    import logging

    logger = logging.getLogger(__name__)

    try:
        from heimdex_common.config import get_config
        from heimdex_common.embeddings.factory import validate_adapter_dimension

        config = get_config()

        logger.info(
            f"Worker startup: validating embedding configuration (VECTOR_SIZE={config.vector_size})"
        )

        # This will raise ValueError if dimensions don't match
        validate_adapter_dimension(config.vector_size)

        logger.info("✓ Startup validation passed: embedding configuration is valid")

    except ValueError as e:
        # Configuration error: log and re-raise to prevent worker startup
        logger.error(f"❌ Startup validation failed: {e}")
        raise
    except ImportError as e:
        # Missing dependencies: log and re-raise
        logger.error(f"❌ Failed to import embedding dependencies: {e}")
        raise
    except Exception as e:
        # Unexpected error during validation
        logger.exception(f"❌ Unexpected error during startup validation: {e}")
        raise


# Run startup validation when module is imported
# This ensures the worker fails fast if configuration is invalid
_validate_startup_configuration()
