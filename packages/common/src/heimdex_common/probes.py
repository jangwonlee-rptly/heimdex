"""
Profile-Aware Dependency Health Probes.

This module provides a robust mechanism for checking the health of external
dependencies (e.g., PostgreSQL, Redis). It is designed to be profile-aware,
meaning it only probes dependencies that are enabled in the current
configuration.

Features include:
-   **Retry with backoff**: Automatically retries failed probes with jittered
    exponential backoff to handle transient failures.
-   **Caching**: Caches successful probe results to reduce overhead and caches
    failed results to prevent excessive probing of a known-down dependency.
-   **Structured logging**: Emits structured JSON logs for easy monitoring and
    analysis of probe attempts.
"""

from __future__ import annotations

import json
import logging
import random
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal, TypedDict

import psycopg2
import redis
from google.api_core import exceptions as gcs_exceptions
from google.cloud import storage

from .config import get_config

# Configure logging
logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


# Cache structure: {dep_name: {"result": DepProbeResult, "expires_at": float}}
class ProbeCacheEntry(TypedDict):
    result: DepProbeResult
    expires_at: float


_probe_cache: dict[str, ProbeCacheEntry] = {}


class DepProbeResult(TypedDict):
    """
    Represents the result of a single dependency probe.

    This `TypedDict` defines the standardized structure for the result of a
    single dependency probe.

    Attributes:
        enabled (bool): Whether the dependency check is enabled.
        skipped (bool): Whether the probe was skipped because it was disabled.
        ok (bool | None): The result of the probe (True for success, False for
            failure). This is `None` if the probe was skipped.
        latency_ms (float | None): The latency of the probe in milliseconds.
        attempts (int): The number of attempts made to probe the dependency.
        reason (str | None): The reason for a failed probe.
    """

    enabled: bool
    skipped: bool
    ok: bool | None
    latency_ms: float | None
    attempts: int
    reason: str | None


class ReadinessResult(TypedDict):
    """
    Represents the uniform readiness response structure.

    This `TypedDict` defines the standardized structure for the overall
    readiness response, which includes the status of all dependencies.

    Attributes:
        service (str): The name of the service.
        env (str): The deployment environment.
        version (str): The version of the service.
        ready (bool): The overall readiness status of the service.
        summary (Literal["ok", "degraded", "down"]): A summary of the
            readiness status.
        deps (dict[str, DepProbeResult]): A dictionary containing the probe
            results for each dependency.
    """

    service: str
    env: str
    version: str
    ready: bool
    summary: Literal["ok", "degraded", "down"]
    deps: dict[str, DepProbeResult]


def _jittered_backoff(attempt: int, base_ms: int = 100, max_ms: int = 200) -> None:
    """
    Sleeps with jittered exponential backoff.

    This function is used to add a delay between probe retries. The delay
    increases exponentially with each attempt, and a random jitter is added
    to prevent a "thundering herd" of retries.

    Args:
        attempt (int): The current retry attempt number.
        base_ms (int): The base delay in milliseconds. Defaults to 100.
        max_ms (int): The maximum delay in milliseconds. Defaults to 200.
    """
    delay_ms = min(base_ms * (2**attempt), max_ms)
    jitter = random.uniform(0.8, 1.2)
    time.sleep((delay_ms * jitter) / 1000)


def _probe_postgres_once(timeout_ms: int) -> tuple[bool, float, str | None]:
    """
    Performs a single attempt to probe the PostgreSQL database.

    Args:
        timeout_ms (int): The timeout for the connection attempt in
            milliseconds.

    Returns:
        tuple[bool, float, str | None]: A tuple containing:
            - A boolean indicating the success of the probe.
            - The latency of the probe in milliseconds.
            - A string reason for the failure, or `None` on success.
    """
    config = get_config()
    start = time.perf_counter()
    try:
        conn = psycopg2.connect(
            config.get_postgres_dsn(),
            connect_timeout=timeout_ms // 1000,
        )
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                result = cur.fetchone()
                elapsed_ms = (time.perf_counter() - start) * 1000
                if result and result[0] == 1:
                    return (True, elapsed_ms, None)
                return (False, elapsed_ms, "unexpected_result")
        finally:
            conn.close()
    except psycopg2.OperationalError as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        if "timeout" in str(e).lower():
            return (False, elapsed_ms, "timeout")
        return (False, elapsed_ms, f"connection_error: {type(e).__name__}")
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return (False, elapsed_ms, f"exception: {type(e).__name__}")


def _probe_redis_once(timeout_ms: int) -> tuple[bool, float, str | None]:
    """
    Performs a single attempt to probe the Redis server.

    Args:
        timeout_ms (int): The timeout for the connection attempt in
            milliseconds.

    Returns:
        tuple[bool, float, str | None]: A tuple containing the success status,
            latency, and an optional failure reason.
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
        elapsed_ms = (time.perf_counter() - start) * 1000
        if result:
            return (True, elapsed_ms, None)
        return (False, elapsed_ms, "ping_failed")
    except redis.exceptions.TimeoutError:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return (False, elapsed_ms, "timeout")
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return (False, elapsed_ms, f"exception: {type(e).__name__}")


def _probe_qdrant_once(timeout_ms: int) -> tuple[bool, float, str | None]:
    """
    Performs a single attempt to probe the Qdrant vector database.

    Args:
        timeout_ms (int): The timeout for the HTTP request in milliseconds.

    Returns:
        tuple[bool, float, str | None]: A tuple containing the success status,
            latency, and an optional failure reason.
    """
    import requests

    config = get_config()
    start = time.perf_counter()
    try:
        response = requests.get(
            f"{config.qdrant_url}/",
            timeout=timeout_ms / 1000,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        if response.status_code == 200:
            return (True, elapsed_ms, None)
        return (False, elapsed_ms, f"http_{response.status_code}")
    except requests.exceptions.Timeout:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return (False, elapsed_ms, "timeout")
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return (False, elapsed_ms, f"exception: {type(e).__name__}")


def _probe_gcs_once(timeout_ms: int) -> tuple[bool, float, str | None]:
    """
    Performs a single attempt to probe the GCS-compatible storage.

    Args:
        timeout_ms (int): The timeout for the GCS request in milliseconds.

    Returns:
        tuple[bool, float, str | None]: A tuple containing the success status,
            latency, and an optional failure reason.
    """
    config = get_config()
    start = time.perf_counter()
    try:
        client = storage.Client(project=config.gcs_project_id)
        bucket = client.bucket(config.gcs_bucket)
        exists = bucket.exists(timeout=timeout_ms / 1000)
        elapsed_ms = (time.perf_counter() - start) * 1000

        if exists:
            return (True, elapsed_ms, None)
        return (False, elapsed_ms, "bucket_not_found")
    except gcs_exceptions.NotFound:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return (False, elapsed_ms, "bucket_not_found")
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return (False, elapsed_ms, f"exception: {type(e).__name__}")


ProbeFn = Callable[[int], tuple[bool, float, str | None]]


def _probe_with_retry(
    dep_name: str,
    probe_fn: ProbeFn,
    timeout_ms: int,
    retries: int,
) -> DepProbeResult:
    """
    Probes a dependency with retry and backoff logic.

    This function repeatedly calls a probe function until it succeeds or the
    maximum number of retries is reached. It uses jittered exponential
    backoff between retries.

    Args:
        dep_name (str): The name of the dependency (for logging).
        probe_fn (ProbeFn): The function to call for a single probe attempt.
        timeout_ms (int): The timeout for each probe attempt.
        retries (int): The maximum number of retry attempts.

    Returns:
        DepProbeResult: The aggregated result of the probe attempts.
    """
    attempts = 0
    last_error = None
    total_latency = 0.0

    for attempt in range(retries + 1):
        attempts += 1
        success, latency_ms, error = probe_fn(timeout_ms)
        total_latency += latency_ms

        if success:
            return {
                "enabled": True,
                "skipped": False,
                "ok": True,
                "latency_ms": round(latency_ms, 2),
                "attempts": attempts,
                "reason": None,
            }

        # Log failure attempt (structured JSON)
        log_data = {
            "ts": datetime.now(UTC).isoformat(),
            "level": "ERROR",
            "msg": "probe_failed",
            "dep": dep_name,
            "attempt": attempts,
            "elapsed_ms": round(latency_ms, 2),
            "reason": error,
        }
        logger.error(json.dumps(log_data, separators=(",", ":")))

        last_error = error
        if attempt < retries:
            _jittered_backoff(attempt)

    # All attempts failed
    return {
        "enabled": True,
        "skipped": False,
        "ok": False,
        "latency_ms": round(total_latency / attempts, 2),
        "attempts": attempts,
        "reason": last_error,
    }


def _get_cached_probe(dep_name: str) -> DepProbeResult | None:
    """
    Retrieves a cached probe result if it has not expired.

    Args:
        dep_name (str): The name of the dependency.

    Returns:
        DepProbeResult | None: The cached probe result, or `None` if not
            found or expired.
    """
    now = time.time()
    if dep_name in _probe_cache:
        entry = _probe_cache[dep_name]
        if now < entry["expires_at"]:
            return entry["result"]
    return None


def _cache_probe(
    dep_name: str,
    result: DepProbeResult,
    cache_sec: int,
    cooldown_sec: int,
) -> None:
    """
    Caches a probe result with a TTL based on its success or failure.

    Successful results are cached for a shorter duration, while failed
    results are cached for a longer "cooldown" period to avoid excessive
    probing of a known-down dependency.

    Args:
        dep_name (str): The name of the dependency.
        result (DepProbeResult): The probe result to cache.
        cache_sec (int): The TTL in seconds for successful results.
        cooldown_sec (int): The TTL in seconds for failed results.
    """
    now = time.time()
    ttl = cache_sec if result["ok"] else cooldown_sec

    _probe_cache[dep_name] = {
        "result": result,
        "expires_at": now + ttl,
    }


def probe_dependency(dep_name: str) -> DepProbeResult:
    """
    Probes a single dependency with profile-awareness and caching.

    This function orchestrates the probing of a single dependency. It checks
    if the probe is enabled, retrieves a cached result if available, or
    performs a fresh probe with retry logic.

    Args:
        dep_name (str): The name of the dependency to probe (e.g., "pg",
            "redis").

    Returns:
        DepProbeResult: The result of the dependency probe.
    """
    config = get_config()

    # Check if dependency is enabled
    enabled_map = {
        "pg": config.enable_pg,
        "redis": config.enable_redis,
        "qdrant": config.enable_qdrant,
        "gcs": config.enable_gcs,
    }

    if dep_name not in enabled_map:
        raise ValueError(f"Unknown dependency: {dep_name}")

    if not enabled_map[dep_name]:
        return {
            "enabled": False,
            "skipped": True,
            "ok": None,
            "latency_ms": None,
            "attempts": 0,
            "reason": "disabled",
        }

    # Check cache
    cached = _get_cached_probe(dep_name)
    if cached is not None:
        return cached

    # Perform fresh probe
    probe_fn_map = {
        "pg": _probe_postgres_once,
        "redis": _probe_redis_once,
        "qdrant": _probe_qdrant_once,
        "gcs": _probe_gcs_once,
    }

    result = _probe_with_retry(
        dep_name=dep_name,
        probe_fn=probe_fn_map[dep_name],
        timeout_ms=config.probe_timeout_ms,
        retries=config.probe_retries,
    )

    # Cache the result
    _cache_probe(
        dep_name=dep_name,
        result=result,
        cache_sec=config.probe_cache_sec,
        cooldown_sec=config.probe_cooldown_sec,
    )

    return result


def check_readiness(service: str, version: str) -> ReadinessResult:
    """
    Checks the readiness of all enabled dependencies.

    This function is the main entrypoint for the readiness probe. It probes
    all enabled dependencies and aggregates their results into a single
    readiness response.

    Args:
        service (str): The name of the service (e.g., "api", "worker").
        version (str): The version of the service.

    Returns:
        ReadinessResult: A dictionary with the overall readiness status and
            detailed results for each dependency.
    """
    config = get_config()

    # Probe all dependencies
    deps = {
        "pg": probe_dependency("pg"),
        "redis": probe_dependency("redis"),
        "qdrant": probe_dependency("qdrant"),
        "gcs": probe_dependency("gcs"),
    }

    # Determine readiness: all enabled deps must be ok
    enabled_deps = [dep for dep in deps.values() if dep["enabled"]]
    if not enabled_deps:
        # No deps enabled - always ready (shouldn't happen in practice)
        ready = True
        summary: Literal["ok", "degraded", "down"] = "ok"
    else:
        all_ok = all(dep["ok"] for dep in enabled_deps)
        ready = all_ok
        summary = "ok" if all_ok else "down"

    # Log readiness evaluation (structured JSON)
    deps_ok = [name for name, dep in deps.items() if dep["enabled"] and dep["ok"]]
    deps_fail = [name for name, dep in deps.items() if dep["enabled"] and not dep["ok"]]

    log_data = {
        "ts": datetime.now(UTC).isoformat(),
        "level": "INFO",
        "msg": "readiness_check",
        "service": service,
        "env": config.environment,
        "version": version,
        "ready": ready,
        "summary": summary,
        "deps_ok": deps_ok,
        "deps_fail": deps_fail,
    }
    logger.info(json.dumps(log_data, separators=(",", ":")))

    return {
        "service": service,
        "env": config.environment,
        "version": version,
        "ready": ready,
        "summary": summary,
        "deps": deps,
    }


def clear_probe_cache() -> None:
    """
    Clears all cached probe results.

    This function is primarily useful for testing, where it may be necessary
    to perform fresh probes in different test cases without being affected by
    cached results.
    """
    global _probe_cache
    _probe_cache = {}
