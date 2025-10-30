"""
Standalone Database Initialization Script.

This script provides a simple, command-line interface for creating the initial
database schema based on the SQLAlchemy models defined in `heimdex_common`. It is
designed to be used in specific scenarios, such as:

1.  **Local Development**: For quickly setting up a fresh database for a developer
    to start working.
2.  **CI/CD Pipelines**: For creating an ephemeral database for integration tests.
3.  **Initial Deployment**: For bootstrapping the very first deployment of the
    application in a new environment.

Usage:
To run this script, execute it as a module from the root of the project:
    python -m heimdex_api.db_init

Important Note on Production Environments:
This script is **not** a database migration tool. It can only create tables;
it cannot handle schema upgrades (e.g., adding a column) on an existing
database. For production environments, it is strongly recommended to use a
dedicated migration tool like Alembic, which provides versioning and the ability
to safely apply incremental changes to a live database.
"""

from __future__ import annotations

# This script imports the `init_db` function from the common package, which
# contains the core logic for connecting to the database and creating tables
# based on the SQLAlchemy model metadata.
from heimdex_common.db import init_db


def main() -> None:
    """
    The main function that orchestrates the database initialization.

    This function prints informative messages to the console to indicate the
    start and successful completion of the schema creation process. It calls
    the centralized `init_db` function to perform the actual database work.
    """
    print("Initializing database schema...")
    init_db()
    print("Database schema initialized successfully.")


# The `if __name__ == "__main__"` block ensures that the `main()` function is
# called only when the script is executed directly, not when it is imported
# as a module into another script.
if __name__ == "__main__":
    main()
