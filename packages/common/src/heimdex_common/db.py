"""
Database Connection and Session Management.

This module provides utilities for managing database connections and sessions
using SQLAlchemy. It includes functions for creating a global engine and
session factory, as well as a context manager for providing transactional
sessions.

The `get_db` context manager is the recommended way to interact with the
database, as it ensures that sessions are properly handled and transactions
are committed or rolled back as needed.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_config
from .models import Base

# Global engine and session factory (lazy loaded)
_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """
    Retrieves or creates the global SQLAlchemy engine.

    This function implements a singleton pattern for the SQLAlchemy engine to
    ensure that only one engine is created per process. The engine is configured
    with a connection pool and pre-ping to handle transient connection issues.

    Returns:
        Engine: The global SQLAlchemy `Engine` instance.
    """
    global _engine
    if _engine is None:
        config = get_config()
        _engine = create_engine(
            config.get_database_url(),
            pool_pre_ping=True,  # Verify connections before using
            pool_size=5,
            max_overflow=10,
        )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """
    Retrieves or creates the global SQLAlchemy session factory.

    This function creates a `sessionmaker` instance that is bound to the
    global engine. The session factory is configured to not autocommit or
    autoflush, giving explicit control over transaction boundaries.

    Returns:
        sessionmaker[Session]: The global SQLAlchemy `sessionmaker` instance.
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
    Provides a transactional database session as a context manager.

    This is the recommended way to interact with the database. It provides a
    SQLAlchemy session from the session factory and handles the session's
    lifecycle. On successful exit from the context, the transaction is
    committed. If an exception occurs, the transaction is rolled back. In
    both cases, the session is always closed.

    Yields:
        Generator[Session, None, None]: A SQLAlchemy `Session` object.
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
    Creates all tables defined in the SQLAlchemy models.

    This function is intended for use in development and testing environments.
    For production environments, it is strongly recommended to use a database
    migration tool like Alembic to manage schema changes.
    """
    engine = get_engine()
    Base.metadata.create_all(bind=engine)


def drop_tables() -> None:
    """
    Drops all tables defined in the SQLAlchemy models.

    Warning:
        This is a destructive operation and should only be used in development
        and testing environments. It will result in the loss of all data.
    """
    engine = get_engine()
    Base.metadata.drop_all(bind=engine)


def init_db() -> None:
    """
    A backward-compatible alias for creating the initial database schema.

    This function is an alias for `create_tables` and is maintained for
    backward compatibility with older scripts.
    """
    create_tables()
