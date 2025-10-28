"""Database initialization script."""

from __future__ import annotations

from heimdex_common.db import init_db


def main() -> None:
    """
    Initialize the database schema.

    This function connects to the database and executes the necessary SQL statements
    to create the initial table structure required by the application. It prints
    status messages to the console before and after the schema initialization.
    """
    print("Initializing database schema...")
    init_db()
    print("Database schema initialized successfully.")


if __name__ == "__main__":
    main()
