"""
Vector database integration for Heimdex.

This package provides abstractions for working with vector databases,
currently supporting Qdrant for similarity search and retrieval.
"""

from heimdex_common.vector.qdrant_repo import (
    ensure_collection,
    point_id_for,
    search,
    upsert_point,
)

__all__ = [
    "ensure_collection",
    "point_id_for",
    "search",
    "upsert_point",
]
