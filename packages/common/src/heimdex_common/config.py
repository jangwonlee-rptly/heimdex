"""
Configuration Management for Heimdex Services.

This module provides a centralized configuration solution using Pydantic's
`BaseSettings`. It allows for type-safe configuration management from
environment variables and `.env` files.

The `HeimdexConfig` class defines all available configuration parameters,
and the `get_config` function provides a singleton instance of the
configuration for use throughout the application.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class HeimdexConfig(BaseSettings):
    """
    Centralized configuration for Heimdex services using Pydantic BaseSettings.

    This class defines the complete set of configuration parameters required
    by the application. It loads values from environment variables, with
    sensible defaults provided for local development. For production
    environments, all required values must be explicitly set.

    The `model_config` attribute is used to configure the behavior of Pydantic,
    including the path to the `.env` file.

    Attributes:
        environment (Literal["local", "dev", "staging", "prod"]): The deployment
            environment, which can affect logging levels and other behaviors.
        version (str): The version of the service, typically injected at
            build time.
        pghost (str): The hostname of the PostgreSQL database.
        pgport (int): The port of the PostgreSQL database.
        pguser (str): The username for the PostgreSQL database.
        pgpassword (str): The password for the PostgreSQL database.
        pgdatabase (str): The name of the PostgreSQL database.
        redis_url (str): The connection URL for the Redis server.
        qdrant_url (str): The HTTP API URL for the Qdrant vector database.
        gcs_endpoint (str): The endpoint for a GCS-compatible storage service,
            used for local development with MinIO.
        gcs_bucket (str): The name of the GCS bucket for asset storage.
        gcs_project_id (str): The GCS project ID.
        gcs_use_ssl (bool): Whether to use SSL for GCS connections.
        google_application_credentials (str | None): The path to the GCS
            service account JSON file.
        enable_pg (bool): A flag to enable or disable the PostgreSQL
            dependency check in the readiness probe.
        enable_redis (bool): A flag to enable or disable the Redis dependency
            check in the readiness probe.
        enable_qdrant (bool): A flag to enable or disable the Qdrant
            dependency check in the readiness probe.
        enable_gcs (bool): A flag to enable or disable the GCS dependency
            check in the readiness probe.
        probe_timeout_ms (int): The timeout in milliseconds for dependency
            probes.
        probe_retries (int): The number of retries for failed dependency
            probes.
        probe_cooldown_sec (int): The cooldown period in seconds for failed
            dependency probes.
        probe_cache_sec (int): The cache duration in seconds for successful
            dependency probes.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Runtime environment
    environment: Literal["local", "dev", "staging", "prod"] = Field(
        default="local",
        alias="HEIMDEX_ENV",
        description="Deployment environment",
    )
    version: str = Field(
        default="0.0.0",
        alias="VERSION",
        description="Service version",
    )

    # PostgreSQL connection
    pghost: str = Field(
        default="localhost",
        alias="PGHOST",
        description="PostgreSQL host",
    )
    pgport: int = Field(
        default=5432,
        alias="PGPORT",
        description="PostgreSQL port",
    )
    pguser: str = Field(
        default="heimdex",
        alias="PGUSER",
        description="PostgreSQL user",
    )
    pgpassword: str = Field(
        default="heimdex",
        alias="PGPASSWORD",
        description="PostgreSQL password",
    )
    pgdatabase: str = Field(
        default="heimdex",
        alias="PGDATABASE",
        description="PostgreSQL database name",
    )

    # Redis connection
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        alias="REDIS_URL",
        description="Redis connection URL",
    )

    # Qdrant connection
    qdrant_url: str = Field(
        default="http://localhost:6333",
        alias="QDRANT_URL",
        description="Qdrant HTTP API URL",
    )

    # GCS emulator connection
    gcs_endpoint: str = Field(
        default="http://localhost:4443",
        alias="GCS_ENDPOINT",
        description="GCS-compatible storage endpoint",
    )
    gcs_bucket: str = Field(
        default="heimdex-dev",
        alias="GCS_BUCKET",
        description="GCS bucket name",
    )
    gcs_project_id: str = Field(
        default="heimdex-local",
        alias="GCS_PROJECT_ID",
        description="GCS project ID",
    )
    gcs_use_ssl: bool = Field(
        default=False,
        alias="GCS_USE_SSL",
        description="Use SSL for GCS connections",
    )
    google_application_credentials: str | None = Field(
        default=None,
        alias="GOOGLE_APPLICATION_CREDENTIALS",
        description="Path to GCS service account JSON",
    )

    # Dependency enablement flags (profile-aware readiness)
    enable_pg: bool = Field(
        default=True,
        alias="ENABLE_PG",
        description="Enable PostgreSQL dependency check",
    )
    enable_redis: bool = Field(
        default=True,
        alias="ENABLE_REDIS",
        description="Enable Redis dependency check",
    )
    enable_qdrant: bool = Field(
        default=False,
        alias="ENABLE_QDRANT",
        description="Enable Qdrant dependency check",
    )
    enable_gcs: bool = Field(
        default=False,
        alias="ENABLE_GCS",
        description="Enable GCS dependency check",
    )

    # Probe tunables
    probe_timeout_ms: int = Field(
        default=300,
        alias="PROBE_TIMEOUT_MS",
        description="Probe timeout in milliseconds",
    )
    probe_retries: int = Field(
        default=2,
        alias="PROBE_RETRIES",
        description="Number of probe retries",
    )
    probe_cooldown_sec: int = Field(
        default=30,
        alias="PROBE_COOLDOWN_SEC",
        description="Cooldown period for failed probes (seconds)",
    )
    probe_cache_sec: int = Field(
        default=10,
        alias="PROBE_CACHE_SEC",
        description="Cache duration for successful probes (seconds)",
    )

    @field_validator("pgport")
    @classmethod
    def validate_pgport(cls, v: int) -> int:
        """
        Validates that the PostgreSQL port is in the valid range.

        Args:
            v (int): The PostgreSQL port to validate.

        Returns:
            int: The validated PostgreSQL port.

        Raises:
            ValueError: If the port is not in the range 1-65535.
        """
        if not (1 <= v <= 65535):
            raise ValueError(f"Invalid PostgreSQL port: {v} (must be 1-65535)")
        return v

    @field_validator("probe_timeout_ms")
    @classmethod
    def validate_probe_timeout(cls, v: int) -> int:
        """
        Clamps the probe timeout to a reasonable range (50-5000ms).

        Args:
            v (int): The probe timeout in milliseconds.

        Returns:
            int: The clamped probe timeout.
        """
        if v < 50:
            return 50
        if v > 5000:
            return 5000
        return v

    @field_validator("probe_retries")
    @classmethod
    def validate_probe_retries(cls, v: int) -> int:
        """
        Clamps the probe retries to a reasonable range (0-5).

        Args:
            v (int): The number of probe retries.

        Returns:
            int: The clamped number of probe retries.
        """
        if v < 0:
            return 0
        if v > 5:
            return 5
        return v

    @field_validator("probe_cooldown_sec")
    @classmethod
    def validate_probe_cooldown(cls, v: int) -> int:
        """
        Clamps the probe cooldown to a reasonable range (5-300s).

        Args:
            v (int): The probe cooldown in seconds.

        Returns:
            int: The clamped probe cooldown.
        """
        if v < 5:
            return 5
        if v > 300:
            return 300
        return v

    @field_validator("probe_cache_sec")
    @classmethod
    def validate_probe_cache(cls, v: int) -> int:
        """
        Clamps the probe cache to a reasonable range (1-60s).

        Args:
            v (int): The probe cache duration in seconds.

        Returns:
            int: The clamped probe cache duration.
        """
        if v < 1:
            return 1
        if v > 60:
            return 60
        return v

    def get_database_url(self, driver: str = "postgresql+psycopg2") -> str:
        """
        Constructs the SQLAlchemy database URL from the configuration.

        Args:
            driver (str): The SQLAlchemy driver string. Defaults to
                "postgresql+psycopg2".

        Returns:
            str: The complete database connection URL.
        """
        return f"{driver}://{self.pguser}:{self.pgpassword}@{self.pghost}:{self.pgport}/{self.pgdatabase}"

    def get_postgres_dsn(self) -> str:
        """
        Constructs the PostgreSQL connection string (DSN) for psycopg2.

        Returns:
            str: The PostgreSQL connection string.
        """
        return f"postgresql://{self.pguser}:{self.pgpassword}@{self.pghost}:{self.pgport}/{self.pgdatabase}"

    def log_summary(self, redact_secrets: bool = True) -> dict[str, str]:
        """
        Generates a redacted configuration summary for logging.

        This method provides a safe way to log the configuration by redacting
        sensitive values like passwords.

        Args:
            redact_secrets (bool): If True, sensitive values are replaced
                with '***'. Defaults to True.

        Returns:
            dict[str, str]: A dictionary of configuration values suitable for
                logging.
        """
        summary = {
            "environment": self.environment,
            "version": self.version,
            "pghost": self.pghost,
            "pgport": str(self.pgport),
            "pgdatabase": self.pgdatabase,
            "pguser": self.pguser if not redact_secrets else "***",
            "redis_url": self._redact_url(self.redis_url) if redact_secrets else self.redis_url,
            "qdrant_url": self.qdrant_url,
            "gcs_endpoint": self.gcs_endpoint,
            "gcs_bucket": self.gcs_bucket,
            "gcs_project_id": self.gcs_project_id,
        }
        return summary

    @staticmethod
    def _redact_url(url: str) -> str:
        """
        Redacts the password from a URL string.

        Args:
            url (str): The URL to redact.

        Returns:
            str: The redacted URL.
        """
        if "@" in url and "://" in url:
            scheme, rest = url.split("://", 1)
            if "@" in rest:
                auth, host = rest.split("@", 1)
                if ":" in auth:
                    user, _ = auth.split(":", 1)
                    return f"{scheme}://{user}:***@{host}"
        return url


# Global config instance (lazy loaded)
_config: HeimdexConfig | None = None


def get_config() -> HeimdexConfig:
    """
    Retrieves the global configuration instance.

    This function implements a singleton pattern to ensure that the
    configuration is loaded only once per process. It lazy-loads the
    configuration on the first call.

    Returns:
        HeimdexConfig: The global `HeimdexConfig` instance.

    Raises:
        pydantic.ValidationError: If any required configuration values are
            missing or invalid.
    """
    global _config
    if _config is None:
        _config = HeimdexConfig()
    return _config


def reset_config() -> None:
    """
    Resets the global configuration instance.

    This function is primarily used for testing to allow for reloading the
    configuration with different settings in different test cases.
    """
    global _config
    _config = None
