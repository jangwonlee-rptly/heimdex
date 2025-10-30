"""
Utility Functions for Job Key Generation and Payload Canonicalization.

This module provides deterministic job_key generation to ensure idempotent job
creation. The job_key is computed as a SHA256 hash of the organization ID,
operation type, and a stable JSON representation of the payload.

This prevents duplicate jobs from being created when the same logical operation
is requested multiple times, providing server-side idempotency guarantees.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID


def stable_dumps(obj: dict[str, Any]) -> str:
    """
    Serializes a dictionary to a canonical JSON string.

    This function ensures that the same logical dictionary always produces the
    same JSON string, regardless of key insertion order. This is critical for
    generating deterministic hashes.

    Args:
        obj: The dictionary to serialize.

    Returns:
        A compact, sorted JSON string.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def make_job_key(org_id: UUID, op_type: str, payload: dict[str, Any]) -> str:
    """
    Generates a deterministic job key for idempotency.

    The job key is computed as:
        SHA256("{org_id}:{op_type}:{stable_json(payload)}")

    This ensures that the same logical job request always produces the same
    job_key, preventing duplicate job creation while preserving multi-tenancy.

    Args:
        org_id: The UUID of the organization (for tenant isolation).
        op_type: The type of operation (e.g., "video_ingest", "mock_process").
        payload: A dictionary containing the job-specific parameters that
                 uniquely identify this job. Should only include fields that
                 affect idempotency (e.g., input file path), not transient
                 fields like request timestamps.

    Returns:
        A 64-character hexadecimal SHA256 hash string.

    Example:
        >>> org_id = UUID("550e8400-e29b-41d4-a716-446655440000")
        >>> key = make_job_key(org_id, "mock_process", {"video_id": "abc123"})
        >>> len(key)
        64
    """
    # Construct the canonical input string
    canonical = f"{org_id}:{op_type}:{stable_dumps(payload)}"
    # Hash it using SHA256
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
