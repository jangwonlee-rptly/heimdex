"""Dependency health probes for readiness checks."""

from __future__ import annotations

import time
from typing import TypedDict

import psycopg2
import redis
from google.api_core import exceptions as gcs_exceptions
from google.cloud import storage

from .config import get_config


class ProbeResult(TypedDict):
    """Result of a dependency health probe."""

    ok: bool
    ms: float
    error: str | None


class ProbesResult(TypedDict):
    """Aggregate result of all dependency probes."""

    deps: dict[str, ProbeResult]


def probe_postgres(timeout_ms: int = 1000) -> ProbeResult:
    """
    Probe PostgreSQL connectivity with a simple SELECT 1 query.

    Args:
        timeout_ms: Timeout in milliseconds (default: 1000)

    Returns:
        ProbeResult with status and timing
    """
    config = get_config()
    start = time.perf_counter()
    try:
        # Use psycopg2 directly for a lightweight probe (no SQLAlchemy overhead)
        conn = psycopg2.connect(
            config.get_postgres_dsn(),
            connect_timeout=timeout_ms // 1000,  # psycopg2 uses seconds
        )
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                result = cur.fetchone()
                if result and result[0] == 1:
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    return {"ok": True, "ms": round(elapsed_ms, 2), "error": None}
                else:
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    return {"ok": False, "ms": round(elapsed_ms, 2), "error": "Unexpected result"}
        finally:
            conn.close()
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {"ok": False, "ms": round(elapsed_ms, 2), "error": str(e)}


def probe_redis(timeout_ms: int = 1000) -> ProbeResult:
    """
    Probe Redis connectivity with a PING command.

    Args:
        timeout_ms: Timeout in milliseconds (default: 1000)

    Returns:
        ProbeResult with status and timing
    """
    config = get_config()
    start = time.perf_counter()
    try:
        client = redis.from_url(
            config.redis_url,
            socket_timeout=timeout_ms / 1000,
            socket_connect_timeout=timeout_ms / 1000,
        )
        result = client.ping()
        if result:
            elapsed_ms = (time.perf_counter() - start) * 1000
            return {"ok": True, "ms": round(elapsed_ms, 2), "error": None}
        else:
            elapsed_ms = (time.perf_counter() - start) * 1000
            return {"ok": False, "ms": round(elapsed_ms, 2), "error": "PING returned False"}
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {"ok": False, "ms": round(elapsed_ms, 2), "error": str(e)}


def probe_qdrant(timeout_ms: int = 1000) -> ProbeResult:
    """
    Probe Qdrant connectivity with a GET / or /readyz request.

    Args:
        timeout_ms: Timeout in milliseconds (default: 1000)

    Returns:
        ProbeResult with status and timing
    """
    import requests

    config = get_config()
    start = time.perf_counter()
    try:
        # Try /readyz first (common k8s pattern), fallback to / if not available
        response = requests.get(
            f"{config.qdrant_url}/",
            timeout=timeout_ms / 1000,
        )
        if response.status_code == 200:
            elapsed_ms = (time.perf_counter() - start) * 1000
            return {"ok": True, "ms": round(elapsed_ms, 2), "error": None}
        else:
            elapsed_ms = (time.perf_counter() - start) * 1000
            return {
                "ok": False,
                "ms": round(elapsed_ms, 2),
                "error": f"HTTP {response.status_code}",
            }
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {"ok": False, "ms": round(elapsed_ms, 2), "error": str(e)}


def probe_gcs(timeout_ms: int = 2000) -> ProbeResult:
    """
    Probe GCS/emulator connectivity by checking bucket existence.

    Args:
        timeout_ms: Timeout in milliseconds (default: 2000, higher for GCS emulator cold start)

    Returns:
        ProbeResult with status and timing
    """
    config = get_config()
    start = time.perf_counter()
    try:
        # Create storage client
        # Note: For emulator, STORAGE_EMULATOR_HOST env var should be set
        client = storage.Client(
            project=config.gcs_project_id,
        )
        # Check if bucket exists
        bucket = client.bucket(config.gcs_bucket)
        exists = bucket.exists(timeout=timeout_ms / 1000)

        if exists:
            elapsed_ms = (time.perf_counter() - start) * 1000
            return {"ok": True, "ms": round(elapsed_ms, 2), "error": None}
        else:
            elapsed_ms = (time.perf_counter() - start) * 1000
            return {
                "ok": False,
                "ms": round(elapsed_ms, 2),
                "error": f"Bucket {config.gcs_bucket} does not exist",
            }
    except gcs_exceptions.NotFound:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {
            "ok": False,
            "ms": round(elapsed_ms, 2),
            "error": f"Bucket {config.gcs_bucket} not found",
        }
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {"ok": False, "ms": round(elapsed_ms, 2), "error": str(e)}


def probe_all_dependencies(
    timeout_ms: int = 1000,
) -> ProbesResult:
    """
    Run all dependency probes and return aggregated results.

    Args:
        timeout_ms: Timeout in milliseconds for each probe (default: 1000)

    Returns:
        ProbesResult with status for each dependency
    """
    return {
        "deps": {
            "pg": probe_postgres(timeout_ms),
            "redis": probe_redis(timeout_ms),
            "qdrant": probe_qdrant(timeout_ms),
            "gcs": probe_gcs(timeout_ms * 2),  # GCS gets more time for cold start
        }
    }


def is_ready(probes: ProbesResult) -> bool:
    """
    Check if all dependencies are ready.

    Args:
        probes: ProbesResult from probe_all_dependencies()

    Returns:
        True if all dependencies are ok, False otherwise
    """
    return all(probe["ok"] for probe in probes["deps"].values())
