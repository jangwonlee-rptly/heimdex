"""
Database Connection and Session Management for SQLAlchemy.

This module abstracts the complexities of setting up and managing database
connections and sessions with SQLAlchemy. It follows best practices for
performance and reliability, such as using a connection pool, ensuring
transactional integrity, and providing a clear, safe interface for
interacting with the database.

Key Components:
- **Global Engine**: A singleton SQLAlchemy `Engine` is created to manage a
  pool of database connections, which is more efficient than creating new
  connections for every request.
- **Session Factory**: A `sessionmaker` is configured to produce new `Session`
  objects, which are the primary interface for all database operations.
- **Transactional Context Manager**: The `get_db` context manager is the
  cornerstone of this module. It provides a `Session` within a well-defined
  transactional scope, automatically handling commits, rollbacks, and
  session closing. This pattern prevents resource leaks and ensures data
  consistency.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_config
from .models import Base

# --- Global, Lazy-Loaded SQLAlchemy Objects ---
# These are initialized as `None` and will be created on their first use.
# This "lazy loading" approach avoids creating database connections when the
# module is simply imported, which is useful for running tools or scripts
# that don't require a database.

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """
    Retrieves the global SQLAlchemy engine, creating it if necessary.

    This function implements a singleton pattern for the SQLAlchemy `Engine`.
    The engine is the core of SQLAlchemy's connectivity, managing a pool of
    connections to the database. Creating it only once per application process
    is crucial for performance and resource management.

    The engine is configured with:
    - `pool_pre_ping=True`: This setting helps SQLAlchemy to detect and handle
      "dead" connections in the pool, making the application more resilient
      to transient network issues or database restarts.
    - A connection pool (`pool_size`, `max_overflow`): This allows the
      application to reuse database connections, avoiding the overhead of
      establishing a new connection for every query.

    Returns:
        Engine: The singleton SQLAlchemy `Engine` instance for the application.
    """
    global _engine
    if _engine is None:
        config = get_config()
        _engine = create_engine(
            config.get_database_url(),
            pool_pre_ping=True,
            pool_size=5,  # The number of connections to keep open in the pool.
            max_overflow=10,  # The number of extra connections that can be opened.
        )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """
    Retrieves the global SQLAlchemy session factory, creating it if necessary.

    A `sessionmaker` is a factory that produces new `Session` objects when called.
    This function creates a singleton factory that is bound to the global engine.

    The sessions created by this factory are configured with:
    - `autocommit=False`: This ensures that all database operations are part of
      a transaction that must be explicitly committed.
    - `autoflush=False`: This prevents the session from automatically issuing
      SQL queries before a commit, giving more explicit control over database
      communication.

    Returns:
        sessionmaker[Session]: The singleton `sessionmaker` instance.
    """
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=get_engine(),
        )
    return _SessionLocal


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """
    Provides a transactional database session via a context manager.

    This is the standard, recommended way to interact with the database in the
    Heimdex application. It ensures that every database operation is performed
    within a safe and predictable transactional block.

    Usage:
    ```
    with get_db() as session:
        # Perform database operations with the session object
        user = session.query(User).filter_by(id=1).first()
        if user:
            user.name = "new name"
    # When the block exits successfully, the transaction is committed.
    # If an exception is raised inside the block, the transaction is rolled back.
    # In all cases, the session is properly closed, releasing the connection
    # back to the pool.
    ```

    Yields:
        Session: A new SQLAlchemy `Session` object ready for use.
    """
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_tables() -> None:
    """
    Creates all database tables defined in the SQLAlchemy declarative models.

    This function inspects the `Base.metadata` object, which collects all classes
    that inherit from the declarative `Base`, and issues `CREATE TABLE` statements
    to the database for any tables that do not already exist.

    Note:
        This function is suitable for setting up a database for the first time
        in a development or testing environment. However, for managing schema
        changes in a production environment (e.g., adding a new column), a
        dedicated database migration tool like Alembic is the recommended
        approach, as it provides versioning and repeatable schema migrations.
    """
    engine = get_engine()
    Base.metadata.create_all(bind=engine)


def drop_tables() -> None:
    """
    Drops all database tables defined in the SQLAlchemy declarative models.

    This function issues `DROP TABLE` statements for all tables associated with
    the `Base.metadata`.

    Warning:
        This is a highly destructive operation that will permanently delete all
        tables and all data within them. It should only be used in controlled
        development and testing scenarios, for example, to reset a database to
        a clean state before running a test suite.
    """
    engine = get_engine()
    Base.metadata.drop_all(bind=engine)


def init_db() -> None:
    """
    A convenience function to initialize the database schema.

    This function is an alias for `create_tables`. It is provided for clarity
    in scripts or initialization routines where the intent is to set up the
    initial database schema.
    """
    create_tables()
