"""Configuration management for Heimdex services."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class HeimdexConfig(BaseSettings):
    """
    Centralized configuration for Heimdex services.

    All configuration values are read from environment variables with sensible defaults
    for local development. Production environments must explicitly set all required values.
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

    @field_validator("pgport")
    @classmethod
    def validate_pgport(cls, v: int) -> int:
        """Ensure PostgreSQL port is in valid range."""
        if not (1 <= v <= 65535):
            raise ValueError(f"Invalid PostgreSQL port: {v} (must be 1-65535)")
        return v

    def get_database_url(self, driver: str = "postgresql+psycopg2") -> str:
        """
        Construct SQLAlchemy database URL.

        Args:
            driver: SQLAlchemy driver string (default: postgresql+psycopg2)

        Returns:
            Complete database connection URL
        """
        return f"{driver}://{self.pguser}:{self.pgpassword}@{self.pghost}:{self.pgport}/{self.pgdatabase}"

    def get_postgres_dsn(self) -> str:
        """
        Construct PostgreSQL connection string for psycopg2.

        Returns:
            PostgreSQL connection string
        """
        return f"postgresql://{self.pguser}:{self.pgpassword}@{self.pghost}:{self.pgport}/{self.pgdatabase}"

    def log_summary(self, redact_secrets: bool = True) -> dict[str, str]:
        """
        Generate a redacted configuration summary for logging.

        Args:
            redact_secrets: If True, replace sensitive values with '***'

        Returns:
            Dictionary of configuration values suitable for logging
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
        """Redact password from URL."""
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
    Get the global configuration instance.

    This function uses a singleton pattern to ensure configuration is loaded only once
    per process. It will raise errors if required environment variables are missing.

    Returns:
        The global HeimdexConfig instance

    Raises:
        ValidationError: If required configuration values are missing or invalid
    """
    global _config
    if _config is None:
        _config = HeimdexConfig()
    return _config


def reset_config() -> None:
    """
    Reset the global configuration instance.

    This function is primarily used for testing to force configuration reload.
    """
    global _config
    _config = None
