"""
Data Access Repositories for Heimdex.

This package contains the data access layer for the Heimdex application.
Repositories are responsible for encapsulating the logic for querying and
manipulating data in the database.

Using a repository pattern helps to separate the concerns of data access from
the business logic of the application.
"""

from __future__ import annotations

from .job_repository import JobRepository

__all__ = ["JobRepository"]
