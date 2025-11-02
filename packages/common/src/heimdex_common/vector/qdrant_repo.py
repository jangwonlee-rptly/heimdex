"""
Qdrant Vector Database Repository.

This module provides a clean, functional interface to Qdrant for vector
similarity search operations. It implements deterministic point IDs using
SHA256 hashing to ensure idempotent upsert operations, which is critical
for reliable distributed systems.

Key Design Principles:
- **Deterministic Point IDs**: SHA256 hash of (org_id, asset_id, segment_id,
  model, model_ver) ensures that the same logical entity always maps to the
  same point ID, enabling idempotent upserts.
- **Tenant Isolation**: All operations require org_id, which is stored in the
  payload for filtering and access control.
- **Memoized Client**: Single HTTP client instance is reused across requests
  for connection pooling and performance.
- **Cosine Distance**: Default similarity metric suitable for normalized
  embeddings from most modern models.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from heimdex_common.config import get_config


@lru_cache(maxsize=1)
def client() -> QdrantClient:
    """
    Returns a memoized Qdrant HTTP client instance.

    The client is lazily initialized on first access and reused for all
    subsequent calls. This ensures efficient connection pooling and avoids
    creating multiple client instances.

    Returns:
        QdrantClient: A configured Qdrant client connected to the instance
            specified by the QDRANT_URL configuration parameter.

    Example:
        >>> qdrant = client()
        >>> collections = qdrant.get_collections()
    """
    config = get_config()
    return QdrantClient(url=config.qdrant_url)


def ensure_collection(
    name: str,
    vector_size: int,
    distance: str = "Cosine",
) -> None:
    """
    Creates a Qdrant collection if it does not already exist.

    This function is idempotent: calling it multiple times with the same
    parameters is safe and will not cause errors. If the collection already
    exists, the function returns immediately without modification.

    Args:
        name (str): The name of the collection to create (e.g., "embeddings").
        vector_size (int): The dimensionality of vectors that will be stored
            in this collection. Must match the embedding model's output size.
        distance (str): The distance metric for similarity search. Defaults to
            "Cosine". Valid options: "Cosine", "Euclid", "Dot", "Manhattan".

    Raises:
        ValueError: If the distance metric is not recognized.
        qdrant_client.exceptions.QdrantException: If Qdrant is unreachable
            or returns an error.

    Example:
        >>> ensure_collection("embeddings", vector_size=384, distance="Cosine")
    """
    qdrant = client()

    # Check if collection already exists (idempotent)
    collections = qdrant.get_collections().collections
    if any(coll.name == name for coll in collections):
        return

    # Map string distance to Qdrant Distance enum
    distance_map = {
        "Cosine": Distance.COSINE,
        "Euclid": Distance.EUCLID,
        "Dot": Distance.DOT,
        "Manhattan": Distance.MANHATTAN,
    }

    if distance not in distance_map:
        raise ValueError(
            f"Invalid distance metric: {distance}. Valid options: {list(distance_map.keys())}"
        )

    # Create the collection with the specified vector configuration
    qdrant.create_collection(
        collection_name=name,
        vectors_config=VectorParams(
            size=vector_size,
            distance=distance_map[distance],
        ),
    )


def point_id_for(
    org_id: str,
    asset_id: str,
    segment_id: str,
    model: str,
    model_ver: str,
) -> str:
    """
    Generates a deterministic point ID from entity identifiers.

    This function creates a unique, stable identifier by hashing the combination
    of all input parameters using SHA256 and converting the hash to a UUID format.
    The same inputs will always produce the same point ID, which is essential for
    idempotent upsert operations.

    The point ID includes org_id to ensure tenant isolation at the ID level,
    and includes model/version to allow multiple embeddings of the same content
    from different models to coexist.

    Qdrant requires point IDs to be either unsigned integers or UUIDs. This
    function uses the first 128 bits (16 bytes) of the SHA256 hash to create
    a deterministic UUID.

    Args:
        org_id (str): The organization/tenant ID.
        asset_id (str): The unique identifier of the asset (e.g., document ID).
        segment_id (str): The identifier for a segment within the asset
            (e.g., chunk index, page number).
        model (str): The name of the embedding model used (e.g., "minilm").
        model_ver (str): The version of the embedding model (e.g., "v2").

    Returns:
        str: A deterministic UUID (36 characters with hyphens) that uniquely
            identifies this vector point.

    Example:
        >>> point_id = point_id_for(
        ...     org_id="org_123",
        ...     asset_id="doc_456",
        ...     segment_id="chunk_0",
        ...     model="minilm",
        ...     model_ver="v2"
        ... )
        >>> len(point_id)
        36
    """
    import uuid

    composite_key = f"{org_id}:{asset_id}:{segment_id}:{model}:{model_ver}"
    hash_bytes = hashlib.sha256(composite_key.encode("utf-8")).digest()

    # Use the first 16 bytes of the SHA256 hash to create a deterministic UUID
    # This gives us a valid UUID format that Qdrant accepts
    point_uuid = uuid.UUID(bytes=hash_bytes[:16])
    return str(point_uuid)


def upsert_point(
    collection_name: str,
    point_id: str,
    vector: list[float],
    payload: dict[str, Any],
) -> None:
    """
    Upserts (inserts or updates) a vector point into a Qdrant collection.

    This operation is idempotent: upserting the same point_id multiple times
    with different vectors/payloads will update the existing point rather than
    creating duplicates.

    The payload should always include org_id for tenant isolation and filtering.

    Args:
        collection_name (str): The name of the collection to upsert into.
        point_id (str): A unique identifier for this point (typically generated
            by point_id_for()).
        vector (list[float]): The embedding vector. Must match the collection's
            vector_size.
        payload (dict[str, Any]): Metadata to store with the vector. Should
            include at minimum:
            - org_id (str): For tenant isolation
            - asset_id (str): For referencing the source asset
            - Any other relevant metadata for filtering/display

    Raises:
        qdrant_client.exceptions.QdrantException: If the collection doesn't
            exist or the vector size doesn't match.

    Example:
        >>> upsert_point(
        ...     collection_name="embeddings",
        ...     point_id="abc123...",
        ...     vector=[0.1, 0.2, 0.3, ...],
        ...     payload={
        ...         "org_id": "org_123",
        ...         "asset_id": "doc_456",
        ...         "segment_id": "chunk_0",
        ...         "model": "minilm",
        ...         "text": "Original text content..."
        ...     }
        ... )
    """
    qdrant = client()

    qdrant.upsert(
        collection_name=collection_name,
        wait=True,
        points=[
            PointStruct(
                id=point_id,
                vector=vector,
                payload=payload,
            )
        ],
    )


def search(
    collection_name: str,
    vector: list[float],
    limit: int = 5,
    query_filter: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Searches for similar vectors in a Qdrant collection.

    Performs a vector similarity search and returns the top-k most similar
    points along with their payloads and similarity scores.

    Args:
        collection_name (str): The name of the collection to search.
        vector (list[float]): The query vector to find similar points for.
        limit (int): Maximum number of results to return. Defaults to 5.
        query_filter (dict[str, Any] | None): Optional Qdrant filter to apply
            to the search. Use this for tenant isolation (e.g., filter by org_id)
            or other metadata-based filtering.

    Returns:
        list[dict[str, Any]]: A list of search results, each containing:
            - id (str): The point ID
            - score (float): The similarity score
            - payload (dict): The metadata stored with the point

    Raises:
        qdrant_client.exceptions.QdrantException: If the collection doesn't
            exist or the vector size doesn't match.

    Example:
        >>> from qdrant_client.models import Filter, FieldCondition, MatchValue
        >>> # Search with tenant isolation
        >>> results = search(
        ...     collection_name="embeddings",
        ...     vector=[0.1, 0.2, 0.3, ...],
        ...     limit=5,
        ...     query_filter=Filter(
        ...         must=[
        ...             FieldCondition(
        ...                 key="org_id",
        ...                 match=MatchValue(value="org_123")
        ...             )
        ...         ]
        ...     )
        ... )
        >>> for result in results:
        ...     print(f"Score: {result['score']}, Asset: {result['payload']['asset_id']}")
    """
    qdrant = client()

    search_results = qdrant.search(
        collection_name=collection_name,
        query_vector=vector,
        limit=limit,
        query_filter=query_filter,
    )

    # Convert Qdrant ScoredPoint objects to simple dictionaries
    return [
        {
            "id": str(point.id),
            "score": point.score,
            "payload": point.payload or {},
        }
        for point in search_results
    ]
