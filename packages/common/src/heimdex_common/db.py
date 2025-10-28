"""Database connection and utilities."""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from psycopg2.extensions import connection as Connection


def get_database_url() -> str:
    """Construct database URL from environment variables."""
    user = os.getenv("PGUSER", "heimdex")
    password = os.getenv("PGPASSWORD", "heimdex")
    host = os.getenv("PGHOST", "localhost")
    port = os.getenv("PGPORT", "5432")
    database = os.getenv("PGDATABASE", "heimdex")
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


def get_connection() -> Connection:
    """Create a new database connection."""
    return psycopg2.connect(get_database_url())


@contextmanager
def get_db() -> Generator[Connection, None, None]:
    """Context manager for database connections."""
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
    """Initialize database schema."""
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
