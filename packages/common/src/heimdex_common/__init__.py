"""
Heimdex Common Package.

This package provides shared utilities, configuration, and data models for all
Heimdex services. It is designed to be a reusable library that promotes
consistency and avoids code duplication across the API and worker services.

Key modules include:
-   `config`: Centralized configuration management.
-   `db`: Database connection and session management.
-   `models`: SQLAlchemy data models for the database schema.
-   `repositories`: Data access layer for database operations.
-   `probes`: Health and readiness probes for dependency checking.
"""

__version__ = "0.0.1"
