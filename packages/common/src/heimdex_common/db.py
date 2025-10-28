"""Database connection and utilities."""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from psycopg2.extensions import connection as Connection


def get_database_url() -> str:
    """
    Construct the database connection URL from environment variables.

    This function reads database connection details (user, password, host, port,
    and database name) from environment variables and assembles them into a
    PostgreSQL connection URL.

    Returns:
        The full database connection URL.
    """
    user = os.getenv("PGUSER", "heimdex")
    password = os.getenv("PGPASSWORD", "heimdex")
    host = os.getenv("PGHOST", "localhost")
    port = os.getenv("PGPORT", "5432")
    database = os.getenv("PGDATABASE", "heimdex")
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


def get_connection() -> Connection:
    """
    Create a new database connection.

    This function establishes a new connection to the PostgreSQL database using the
    URL constructed from environment variables.

    Returns:
        A new database connection object.
    """
    return psycopg2.connect(get_database_url())


@contextmanager
def get_db() -> Generator[Connection, None, None]:
    """
    Provide a transactional database connection as a context manager.

    This function yields a database connection that automatically commits on
    successful exit and rolls back on exceptions, ensuring that the connection
    is always closed.

    Yields:
        A database connection object.
    """
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """
    Initialize the database schema by creating tables and indexes.

    This function executes a SQL script to create the `jobs` table and associated
    indexes if they do not already exist, ensuring the database is ready for use.
    """
    schema = """
    CREATE TABLE IF NOT EXISTS jobs (
        id UUID PRIMARY KEY,
        status VARCHAR(20) NOT NULL,
        stage VARCHAR(50),
        progress INTEGER DEFAULT 0,
        result JSONB,
        error TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
    CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC);
    """

    with get_db() as conn, conn.cursor() as cur:
        cur.execute(schema)
