"""
Centralized Configuration Management for Heimdex Services.

This module is the single source of truth for all configuration across the
Heimdex platform. It leverages Pydantic's `BaseSettings` to create a robust,
type-safe, and testable configuration system. The primary goal is to decouple
the application logic from the source of its configuration, whether that be
environment variables, a `.env` file, or secrets management systems.

Core Features:
- **Type Safety**: All configuration parameters are strongly typed, preventing
  common errors caused by incorrect data types.
- **Environment Variable Loading**: Configuration is loaded primarily from
  environment variables, following the 12-Factor App methodology.
- **`.env` File Support**: For local development, a `deploy/.env` file is used
  to provide a convenient way to set environment variables.
- **Validation**: Pydantic performs automatic validation of all incoming data,
  and this module adds custom validators for more complex rules.
- **Singleton Access**: The `get_config` function provides a globally accessible,
  lazy-loaded singleton instance of the configuration, ensuring consistency
  and performance.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class HeimdexConfig(BaseSettings):
    """
    Defines the complete configuration schema for all Heimdex services.

    This class acts as a data contract for the application's configuration.
    Each attribute corresponds to a configuration parameter that can be set
    via an environment variable. The `Field` function from Pydantic is used
    to provide default values, aliases (the actual environment variable name),
    and a clear description for each parameter.

    The `model_config` attribute points to the `.env` file location, ensuring
    that developers can easily get started by copying `deploy/.env.example`.

    The class is organized into logical sections:
    - Runtime Environment: General application settings.
    - Service Connections: Credentials and locations for Postgres, Redis, etc.
    - Dependency Probes: Fine-tuning for the application's health checks.
    - Authentication: Settings for JWT verification (Supabase or development).
    """

    model_config = SettingsConfigDict(
        # For local development, Pydantic will load variables from this file.
        # The path is relative to the project root where the app is run.
        # In production, these should be set directly as environment variables.
        env_file="deploy/.env",
        env_file_encoding="utf-8",
        case_sensitive=True,  # e.g., PGHOST is different from pghost
        extra="ignore",  # Ignore extra environment variables not defined in this model
    )

    # --- Runtime Environment ---
    environment: Literal["local", "dev", "staging", "prod"] = Field(
        default="local",
        alias="HEIMDEX_ENV",
        description=(
            "Defines the deployment environment. This can be used to enable "
            "or disable debugging features, set different logging levels, or "
            "alter other environment-specific behaviors."
        ),
    )
    version: str = Field(
        default="0.0.0",
        alias="VERSION",
        description=(
            "The semantic version of the running service. This is typically "
            "injected into the environment during the build/deployment process "
            "and is useful for logging and monitoring."
        ),
    )

    # --- PostgreSQL Connection ---
    pghost: str = Field(
        default="localhost", alias="PGHOST", description="Hostname of the PostgreSQL database."
    )
    pgport: int = Field(
        default=5432, alias="PGPORT", description="Port of the PostgreSQL database."
    )
    pguser: str = Field(
        default="heimdex", alias="PGUSER", description="Username for the PostgreSQL database."
    )
    pgpassword: str = Field(
        default="heimdex", alias="PGPASSWORD", description="Password for the PostgreSQL database."
    )
    pgdatabase: str = Field(
        default="heimdex", alias="PGDATABASE", description="Name of the PostgreSQL database."
    )

    # --- Redis Connection ---
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        alias="REDIS_URL",
        description=(
            "The full connection URL for the Redis server, used for caching "
            "and as a message broker for the background worker."
        ),
    )

    # --- Qdrant Connection ---
    qdrant_url: str = Field(
        default="http://localhost:6333",
        alias="QDRANT_URL",
        description="The HTTP API endpoint for the Qdrant vector database.",
    )

    # --- GCS (Google Cloud Storage) / MinIO Connection ---
    gcs_endpoint: str = Field(
        default="http://localhost:4443",
        alias="GCS_ENDPOINT",
        description=(
            "The endpoint for a GCS-compatible object storage service. For local "
            "development, this points to a MinIO container."
        ),
    )
    gcs_bucket: str = Field(
        default="heimdex-dev",
        alias="GCS_BUCKET",
        description="The name of the GCS bucket for asset storage.",
    )
    gcs_project_id: str = Field(
        default="heimdex-local", alias="GCS_PROJECT_ID", description="The GCS project ID."
    )
    gcs_use_ssl: bool = Field(
        default=False, alias="GCS_USE_SSL", description="Whether to use SSL for GCS connections."
    )
    google_application_credentials: str | None = Field(
        default=None,
        alias="GOOGLE_APPLICATION_CREDENTIALS",
        description="Path to the GCS service account JSON file for authentication.",
    )

    # --- Dependency Enablement Flags for Readiness Probes ---
    # These flags allow for creating different service "profiles". For example,
    # the API server needs Postgres and Redis, but the worker might not need
    # a direct Postgres connection. This allows readiness probes to be tailored
    # to the specific dependencies of each service.
    enable_pg: bool = Field(
        default=True, alias="ENABLE_PG", description="Enable PostgreSQL dependency check."
    )
    enable_redis: bool = Field(
        default=True, alias="ENABLE_REDIS", description="Enable Redis dependency check."
    )
    enable_qdrant: bool = Field(
        default=False, alias="ENABLE_QDRANT", description="Enable Qdrant dependency check."
    )
    enable_gcs: bool = Field(
        default=False, alias="ENABLE_GCS", description="Enable GCS dependency check."
    )

    # --- Probe Tunables ---
    # These settings control the behavior of the health and readiness probes,
    # allowing for fine-tuning of timeouts, retries, and caching to make the
    # system more resilient to transient failures.
    probe_timeout_ms: int = Field(
        default=300, alias="PROBE_TIMEOUT_MS", description="Probe timeout in milliseconds."
    )
    probe_retries: int = Field(
        default=2, alias="PROBE_RETRIES", description="Number of retries for failed probes."
    )
    probe_cooldown_sec: int = Field(
        default=30,
        alias="PROBE_COOLDOWN_SEC",
        description="Cooldown period for failed probes (seconds).",
    )
    probe_cache_sec: int = Field(
        default=10,
        alias="PROBE_CACHE_SEC",
        description="Cache duration for successful probes (seconds).",
    )

    # --- Authentication Configuration ---
    auth_provider: Literal["supabase", "dev"] = Field(
        default="dev",
        alias="AUTH_PROVIDER",
        description=(
            "The authentication provider to use. 'supabase' for production, "
            "'dev' for local development."
        ),
    )
    supabase_jwks_url: str | None = Field(
        default=None,
        alias="SUPABASE_JWKS_URL",
        description="The URL to the JSON Web Key Set (JWKS) for verifying Supabase JWTs.",
    )
    auth_audience: str | None = Field(
        default=None,
        alias="AUTH_AUDIENCE",
        description="The expected 'aud' (audience) claim in the JWT.",
    )
    auth_issuer: str | None = Field(
        default=None,
        alias="AUTH_ISSUER",
        description="The expected 'iss' (issuer) claim in the JWT.",
    )
    dev_jwt_secret: str = Field(
        default="local-dev-secret",
        alias="DEV_JWT_SECRET",
        description="A shared secret for signing and verifying JWTs in 'dev' mode (uses HS256).",
    )

    @field_validator("pgport")
    @classmethod
    def validate_pgport(cls, v: int) -> int:
        """
        Ensures that the provided PostgreSQL port is within the valid TCP/IP port range.

        Args:
            v (int): The PostgreSQL port number from the configuration.

        Returns:
            int: The validated port number.

        Raises:
            ValueError: If the port is not between 1 and 65535.
        """
        if not (1 <= v <= 65535):
            raise ValueError(f"Invalid PostgreSQL port: {v} (must be 1-65535)")
        return v

    # --- Custom Validators for Probe Tunables ---
    # These validators clamp the probe-related values to sensible ranges to
    # prevent misconfigurations from causing extreme behaviors, like excessively
    # long timeouts or near-instantaneous cooldowns.

    @field_validator("probe_timeout_ms")
    @classmethod
    def validate_probe_timeout(cls, v: int) -> int:
        """Clamps the probe timeout to a reasonable range (50-5000ms)."""
        return max(50, min(v, 5000))

    @field_validator("probe_retries")
    @classmethod
    def validate_probe_retries(cls, v: int) -> int:
        """Clamps the probe retries to a reasonable range (0-5)."""
        return max(0, min(v, 5))

    @field_validator("probe_cooldown_sec")
    @classmethod
    def validate_probe_cooldown(cls, v: int) -> int:
        """Clamps the probe cooldown to a reasonable range (5-300s)."""
        return max(5, min(v, 300))

    @field_validator("probe_cache_sec")
    @classmethod
    def validate_probe_cache(cls, v: int) -> int:
        """Clamps the probe cache to a reasonable range (1-60s)."""
        return max(1, min(v, 60))

    def model_post_init(self, __context: object) -> None:
        """
        Performs post-initialization validation on the configuration.

        This method is a Pydantic hook that runs after the model has been
        fully loaded. It enforces complex validation rules that depend on
        multiple fields.

        Raises:
            ValueError:
                - If `AUTH_PROVIDER` is 'dev' in a 'prod' environment, which is a
                  critical security risk.
                - If `AUTH_PROVIDER` is 'supabase' but the necessary Supabase-
                  specific configuration variables are missing.
        """
        if self.auth_provider == "dev" and self.environment == "prod":
            raise ValueError(
                "AUTH_PROVIDER=dev is not allowed in production (HEIMDEX_ENV=prod). "
                "Use AUTH_PROVIDER=supabase with valid credentials."
            )

        if self.auth_provider == "supabase":
            missing_fields = []
            if not self.supabase_jwks_url:
                missing_fields.append("SUPABASE_JWKS_URL")
            if not self.auth_audience:
                missing_fields.append("AUTH_AUDIENCE")
            if not self.auth_issuer:
                missing_fields.append("AUTH_ISSUER")
            if missing_fields:
                raise ValueError(
                    f"AUTH_PROVIDER=supabase requires the following fields: "
                    f"{', '.join(missing_fields)}"
                )

    def get_database_url(self, driver: str = "postgresql+psycopg2") -> str:
        """
        Constructs the full SQLAlchemy database URL from individual components.

        This method provides a standardized way to create the database connection
        string required by SQLAlchemy, abstracting the details of the URL format.

        Args:
            driver (str): The SQLAlchemy database driver to use. Defaults to
                "postgresql+psycopg2", which is suitable for psycopg version 3.

        Returns:
            str: The complete database connection URL, e.g.,
                "postgresql+psycopg2://user:password@host:port/dbname".
        """
        return f"{driver}://{self.pguser}:{self.pgpassword}@{self.pghost}:{self.pgport}/{self.pgdatabase}"

    def get_postgres_dsn(self) -> str:
        """
        Constructs a PostgreSQL Data Source Name (DSN) connection string.

        This format is often used by lower-level database libraries or tools
        that do not use the SQLAlchemy URL format.

        Returns:
            str: The PostgreSQL DSN, e.g., "postgresql://user:password@host:port/dbname".
        """
        return f"postgresql://{self.pguser}:{self.pgpassword}@{self.pghost}:{self.pgport}/{self.pgdatabase}"

    def log_summary(self, redact_secrets: bool = True) -> dict[str, str | int]:
        """
        Generates a configuration summary suitable for logging at startup.

        This method creates a dictionary of the most important configuration
        values. It is designed to be used with a structured logger to provide
        a clear snapshot of the application's configuration when it starts,
        which is invaluable for debugging.

        Args:
            redact_secrets (bool): If True (the default), sensitive information
                like passwords and secrets will be replaced with '***'.

        Returns:
            dict[str, str | int]: A dictionary of key configuration values.
        """
        return {
            "environment": self.environment,
            "version": self.version,
            "pghost": self.pghost,
            "pgport": self.pgport,
            "pgdatabase": self.pgdatabase,
            "pguser": self.pguser,
            "redis_url": self._redact_url(self.redis_url) if redact_secrets else self.redis_url,
            "qdrant_url": self.qdrant_url,
            "gcs_endpoint": self.gcs_endpoint,
            "gcs_bucket": self.gcs_bucket,
            "auth_provider": self.auth_provider,
        }

    @staticmethod
    def _redact_url(url: str) -> str:
        """
        A simple utility to redact the password from a URL string.

        This is a helper for `log_summary` to avoid accidentally leaking
        credentials into logs.

        Args:
            url (str): The URL containing a potential password (e.g., from Redis).

        Returns:
            str: The URL with the password part replaced by '***'.
        """
        if "@" in url and "://" in url:
            scheme, rest = url.split("://", 1)
            if "@" in rest:
                auth, host = rest.split("@", 1)
                if ":" in auth:
                    user, _ = auth.split(":", 1)
                    return f"{scheme}://{user}:***@{host}"
        return url


# This global variable holds the singleton instance of the configuration.
# It is initialized to None and lazy-loaded by the `get_config` function.
_config: HeimdexConfig | None = None


def get_config() -> HeimdexConfig:
    """
    Provides access to the global, singleton `HeimdexConfig` instance.

    This function is the primary entry point for the rest of the application
    to access configuration values. It implements a singleton pattern to ensure
    that the configuration is loaded from the environment only once, improving
    performance and consistency.

    Returns:
        HeimdexConfig: The single, application-wide configuration instance.

    Raises:
        pydantic.ValidationError: If the environment variables do not match the
            schema defined in `HeimdexConfig` (e.g., missing required fields,
            incorrect types), Pydantic will raise an error on the first call.
    """
    global _config
    if _config is None:
        # If the config has not been loaded yet, create a new instance.
        # This will trigger Pydantic to load and validate from the environment.
        _config = HeimdexConfig()
    return _config


def reset_config() -> None:
    """
    Resets the global configuration singleton.

    This function is intended exclusively for use in testing environments.
    It allows tests to modify environment variables and then reload the
    configuration to test different application behaviors. It should not be
    called in production code.
    """

    global _config
    _config = None
