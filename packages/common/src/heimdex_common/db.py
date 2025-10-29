"""Database connection and session management."""

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
    Get or create the global SQLAlchemy engine.

    Returns:
        SQLAlchemy engine instance
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
    Get or create the global session factory.

    Returns:
        SQLAlchemy sessionmaker instance
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
    Provide a transactional database session as a context manager.

    This function yields a SQLAlchemy session that automatically commits on
    successful exit and rolls back on exceptions, ensuring that the session
    is always closed.

    Yields:
        A SQLAlchemy Session object.
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
    Create all tables defined in SQLAlchemy models.

    This function is primarily for development/testing. In production, use Alembic
    migrations instead.
    """
    engine = get_engine()
    Base.metadata.create_all(bind=engine)


def drop_tables() -> None:
    """
    Drop all tables defined in SQLAlchemy models.

    WARNING: This is destructive and should only be used in development/testing.
    """
    engine = get_engine()
    Base.metadata.drop_all(bind=engine)


def init_db() -> None:
    """Backward-compatible alias for initial schema creation."""
    create_tables()
