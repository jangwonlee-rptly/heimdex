"""
Data Access Layer: Repositories for Heimdex.

This package serves as the data access layer for the Heimdex application,
implementing the Repository Pattern. The primary goal of this pattern is to
create a clean separation between the application's business logic and the
underlying data persistence mechanisms (in this case, a PostgreSQL database
managed by SQLAlchemy).

Core Principles of the Repository Pattern Here:
- **Abstraction**: Repositories provide a simple, object-oriented interface for
  accessing domain objects (e.g., `Job`, `JobEvent`). The rest of the application
  does not need to know about SQLAlchemy sessions, queries, or database tables.
- **Centralized Data Logic**: All logic for querying and manipulating data is
  centralized within the repository classes. This avoids scattering database
  code throughout the application, making it easier to maintain, optimize, and
  test.
- **Testability**: By abstracting the data layer, the business logic can be
  tested independently of the database by using mock or in-memory repositories.

This `__init__.py` file uses the `__all__` variable to define the public API
of the `repositories` package, making it convenient for other parts of the
application to import the available repository classes with a clean syntax,
like `from heimdex_common.repositories import JobRepository`.
"""

from __future__ import annotations

from .job_repository import JobRepository

__all__ = ["JobRepository"]
