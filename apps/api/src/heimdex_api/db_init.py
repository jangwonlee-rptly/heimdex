"""Database initialization script."""

from __future__ import annotations

from heimdex_common.db import init_db


def main() -> None:
    """Run database migrations."""
    print("Initializing database schema...")
    init_db()
    print("Database schema initialized successfully.")


if __name__ == "__main__":
    main()
