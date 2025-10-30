"""
Profile-Aware and Resilient Dependency Health Probes.

This module provides a sophisticated health-checking mechanism for the external
dependencies that Heimdex services rely on, such as PostgreSQL and Redis.
It is designed to be a core component of the application's observability and
resilience strategy, providing the logic for Kubernetes-style readiness and
liveness probes.

Core Principles:
- **Profile-Awareness**: A service should only be considered "unready" if a
  dependency *it actually needs* is down. The probes are "profile-aware,"
  meaning they read the application's configuration to determine which
  dependencies are enabled for the current service instance and only check those.
- **Resilience to Transient Failures**: Network glitches and temporary service
  unavailability are facts of life in distributed systems. This module uses a
  jittered exponential backoff algorithm for retries, preventing a single
  transient failure from taking a service offline.
- **Performance and Low Overhead**: Health probes should not overload the services
  they are checking. This module uses a dual-TTL caching mechanism: successful
  probes are cached for a short period, while failures are cached for a longer
  "cooldown" period. This prevents a service from repeatedly hammering a
  dependency that is known to be down.
- **Structured, Actionable Logging**: Every probe attempt and readiness evaluation
  is logged as a structured JSON object. This makes the health status of the
  system highly observable and easy to integrate with modern logging and
  alerting platforms.
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

# Configure a basic logger to output structured JSON to stdout.
# In a real-world scenario, this would be integrated with a more robust
# logging library, but this approach keeps the module self-contained.
logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


class ProbeCacheEntry(TypedDict):
    """Internal structure for a cached probe result."""
    result: DepProbeResult
    expires_at: float


# The global in-memory cache for probe results.
_probe_cache: dict[str, ProbeCacheEntry] = {}


class DepProbeResult(TypedDict):
    """
    A standardized data structure representing the result of a single dependency probe.

    This TypedDict ensures that all probe functions return a consistent data
    structure, which simplifies aggregation and reporting.

    Attributes:
        enabled: Whether this dependency is configured to be checked.
        skipped: True if the probe was not run because the dependency is disabled.
        ok: The boolean result of the probe (True for success, False for failure).
        latency_ms: The time taken for the final successful or failed probe attempt.
        attempts: The total number of attempts made before reaching a conclusion.
        reason: A short, machine-readable string indicating the cause of failure.
    """

    enabled: bool
    skipped: bool
    ok: bool | None
    latency_ms: float | None
    attempts: int
    reason: str | None


class ReadinessResult(TypedDict):
    """
    A standardized data structure for the overall service readiness response.

    This is the top-level object returned by the readiness check, suitable for
    serialization as a JSON response to a readiness probe request.

    Attributes:
        service: The name of the service being checked (e.g., "api").
        ready: The overall readiness status. True only if all *enabled* deps are ok.
        summary: A high-level summary: "ok", "degraded", or "down".
        deps: A dictionary containing the detailed `DepProbeResult` for each dependency.
    """

    service: str
    env: str
    version: str
    ready: bool
    summary: Literal["ok", "degraded", "down"]
    deps: dict[str, DepProbeResult]


def _jittered_backoff(attempt: int, base_ms: int = 100, max_ms: int = 200) -> None:
    """
    Waits for a period of time calculated with jittered exponential backoff.

    This is a crucial strategy for retrying failed operations in a distributed
    system.
    - **Exponential Backoff**: The delay increases exponentially with each failed
      attempt, which gives a struggling dependency more time to recover.
    - **Jitter**: A small amount of randomness is added to the delay. If multiple
      instances of a service are all retrying at the same time, jitter prevents
      them from retrying in a synchronized, "thundering herd" wave that could
      overwhelm the dependency.

    Args:
        attempt: The current retry attempt number (e.g., 0 for the first retry).
    """
    delay_ms = min(base_ms * (2**attempt), max_ms)
    jitter = random.uniform(0.8, 1.2)  # 20% jitter
    time.sleep((delay_ms * jitter) / 1000)


def _probe_postgres_once(timeout_ms: int) -> tuple[bool, float, str | None]:
    """Performs a single connection attempt to the PostgreSQL database."""
    config = get_config()
    start = time.perf_counter()
    try:
        conn = psycopg2.connect(config.get_postgres_dsn(), connect_timeout=timeout_ms // 1000)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                if cur.fetchone() == (1,):
                    return True, (time.perf_counter() - start) * 1000, None
                return False, (time.perf_counter() - start) * 1000, "unexpected_result"
        finally:
            conn.close()
    except psycopg2.OperationalError as e:
        reason = "timeout" if "timeout" in str(e).lower() else "connection_error"
        return False, (time.perf_counter() - start) * 1000, reason
    except Exception as e:
        return False, (time.perf_counter() - start) * 1000, f"exception:{type(e).__name__}"


def _probe_redis_once(timeout_ms: int) -> tuple[bool, float, str | None]:
    """Performs a single PING command to the Redis server."""
    config = get_config()
    start = time.perf_counter()
    try:
        client = redis.from_url(
            config.redis_url,
            socket_timeout=timeout_ms / 1000,
            socket_connect_timeout=timeout_ms / 1000,
        )
        if client.ping():
            return True, (time.perf_counter() - start) * 1000, None
        return False, (time.perf_counter() - start) * 1000, "ping_failed"
    except redis.exceptions.TimeoutError:
        return False, (time.perf_counter() - start) * 1000, "timeout"
    except Exception as e:
        return False, (time.perf_counter() - start) * 1000, f"exception:{type(e).__name__}"


def _probe_qdrant_once(timeout_ms: int) -> tuple[bool, float, str | None]:
    """Performs a single GET request to the Qdrant root endpoint."""
    import requests
    config = get_config()
    start = time.perf_counter()
    try:
        response = requests.get(f"{config.qdrant_url}/", timeout=timeout_ms / 1000)
        if response.status_code == 200:
            return True, (time.perf_counter() - start) * 1000, None
        return False, (time.perf_counter() - start) * 1000, f"http_{response.status_code}"
    except requests.exceptions.Timeout:
        return False, (time.perf_counter() - start) * 1000, "timeout"
    except Exception as e:
        return False, (time.perf_counter() - start) * 1000, f"exception:{type(e).__name__}"


def _probe_gcs_once(timeout_ms: int) -> tuple[bool, float, str | None]:
    """Performs a single check to verify the existence of the GCS bucket."""
    config = get_config()
    start = time.perf_counter()
    try:
        client = storage.Client(project=config.gcs_project_id)
        bucket = client.bucket(config.gcs_bucket)
        if bucket.exists(timeout=timeout_ms / 1000):
            return True, (time.perf_counter() - start) * 1000, None
        return False, (time.perf_counter() - start) * 1000, "bucket_not_found"
    except gcs_exceptions.NotFound:
        return False, (time.perf_counter() - start) * 1000, "bucket_not_found"
    except Exception as e:
        return False, (time.perf_counter() - start) * 1000, f"exception:{type(e).__name__}"


ProbeFn = Callable[[int], tuple[bool, float, str | None]]


def _probe_with_retry(dep_name: str, probe_fn: ProbeFn, timeout_ms: int, retries: int) -> DepProbeResult:
    """
    A higher-order function that orchestrates the probing of a dependency with retries.

    Args:
        dep_name: The human-readable name of the dependency for logging.
        probe_fn: The specific, single-attempt probe function to be called.
        timeout_ms: The timeout to pass to the probe function.
        retries: The number of times to retry after the initial failed attempt.

    Returns:
        The final `DepProbeResult` after all attempts.
    """
    last_error, total_latency = None, 0.0
    for attempt in range(retries + 1):
        success, latency_ms, error = probe_fn(timeout_ms)
        total_latency += latency_ms
        if success:
            return {
                "enabled": True, "skipped": False, "ok": True,
                "latency_ms": round(latency_ms, 2), "attempts": attempt + 1, "reason": None,
            }
        last_error = error
        logger.error(json.dumps({
            "ts": datetime.now(UTC).isoformat(), "level": "WARN", "msg": "probe_attempt_failed",
            "dep": dep_name, "attempt": attempt + 1, "max_attempts": retries + 1,
            "elapsed_ms": round(latency_ms, 2), "reason": error,
        }, separators=(",", ":")))
        if attempt < retries:
            _jittered_backoff(attempt)
    return {
        "enabled": True, "skipped": False, "ok": False,
        "latency_ms": round(total_latency / (retries + 1), 2), "attempts": retries + 1, "reason": last_error,
    }


def _get_cached_probe(dep_name: str) -> DepProbeResult | None:
    """Retrieves a valid, non-expired probe result from the in-memory cache."""
    entry = _probe_cache.get(dep_name)
    if entry and time.time() < entry["expires_at"]:
        return entry["result"]
    return None


def _cache_probe(dep_name: str, result: DepProbeResult, cache_sec: int, cooldown_sec: int) -> None:
    """
    Caches a probe result with a dual-TTL strategy.

    - If the probe was successful (`ok: True`), it's cached for `cache_sec`.
    - If the probe failed (`ok: False`), it's cached for the longer `cooldown_sec`.
      This prevents the readiness probe from flooding a known-down dependency with
      checks, giving it time to recover.
    """
    ttl = cache_sec if result.get("ok") else cooldown_sec
    _probe_cache[dep_name] = {"result": result, "expires_at": time.time() + ttl}


def probe_dependency(dep_name: str) -> DepProbeResult:
    """
    The main public function for probing a single dependency.

    This function ties everything together: profile-awareness, caching, and
    the retry mechanism. It is the primary building block for the overall
    readiness check.

    Args:
        dep_name: The name of the dependency to probe (e.g., "pg", "redis").

    Returns:
        The result of the dependency probe, from cache or a fresh check.
    """
    config = get_config()
    enabled_map = {
        "pg": config.enable_pg, "redis": config.enable_redis,
        "qdrant": config.enable_qdrant, "gcs": config.enable_gcs,
    }
    if dep_name not in enabled_map:
        raise ValueError(f"Unknown dependency: {dep_name}")
    if not enabled_map[dep_name]:
        return {
            "enabled": False, "skipped": True, "ok": None,
            "latency_ms": None, "attempts": 0, "reason": "disabled",
        }
    if cached := _get_cached_probe(dep_name):
        return cached
    probe_fn_map = {
        "pg": _probe_postgres_once, "redis": _probe_redis_once,
        "qdrant": _probe_qdrant_once, "gcs": _probe_gcs_once,
    }
    result = _probe_with_retry(
        dep_name=dep_name,
        probe_fn=probe_fn_map[dep_name],
        timeout_ms=config.probe_timeout_ms,
        retries=config.probe_retries,
    )
    _cache_probe(
        dep_name=dep_name, result=result,
        cache_sec=config.probe_cache_sec,
        cooldown_sec=config.probe_cooldown_sec,
    )
    return result


def check_readiness(service: str, version: str) -> ReadinessResult:
    """
    Checks the readiness of all enabled dependencies and returns a summary.

    This is the main entrypoint for a readiness probe endpoint. It iterates
    through all potential dependencies, probes the ones that are enabled for
    the current service profile, and aggregates the results into a single,
    comprehensive `ReadinessResult`.

    Args:
        service: The name of the service being checked.
        version: The version of the service.

    Returns:
        A `ReadinessResult` object suitable for JSON serialization.
    """
    config = get_config()
    deps = {
        "pg": probe_dependency("pg"),
        "redis": probe_dependency("redis"),
        "qdrant": probe_dependency("qdrant"),
        "gcs": probe_dependency("gcs"),
    }
    enabled_deps = [dep for dep in deps.values() if dep["enabled"]]
    ready = all(dep["ok"] for dep in enabled_deps) if enabled_deps else True
    summary = "ok" if ready else "down"
    log_data = {
        "ts": datetime.now(UTC).isoformat(), "level": "INFO", "msg": "readiness_check",
        "service": service, "env": config.environment, "version": version, "ready": ready,
        "summary": summary,
        "deps_ok": [name for name, d in deps.items() if d["enabled"] and d["ok"]],
        "deps_fail": [name for name, d in deps.items() if d["enabled"] and not d["ok"]],
    }
    logger.info(json.dumps(log_data, separators=(",", ":")))
    return {
        "service": service, "env": config.environment, "version": version,
        "ready": ready, "summary": summary, "deps": deps,
    }


def clear_probe_cache() -> None:
    """
    Clears all cached probe results. Essential for testing environments.
    """
    global _probe_cache
    _probe_cache.clear()
