"""
Entrypoint for the Heimdex Worker's Lightweight Heartbeat Process.

This module provides a simple, standalone process whose sole responsibility is
to signal that the worker *service* is alive. It does this by emitting a
periodic "heartbeat" log message.

Architectural Note:
This process does **not** perform any actual job processing. In the Heimdex
architecture, job processing is handled by Dramatiq, which runs its own set of
worker processes, typically started via the `dramatiq` command-line tool.

The purpose of this heartbeat process is to serve as a stable, lightweight
entrypoint (`CMD`) for the worker's Docker container. It provides a clear
signal for container orchestration systems (like Kubernetes) that the container
is running, without the overhead of the full job processing environment. This
separation makes the system more robust and easier to monitor.

The process is designed to be resilient, with graceful shutdown handling for
`SIGTERM` and `SIGINT` signals.
"""

from __future__ import annotations

import os
import signal
import sys
from threading import Event

from .logger import log_event

# The interval in seconds at which the heartbeat log is emitted.
_HEARTBEAT_INTERVAL = int(os.getenv("HEIMDEX_HEARTBEAT_INTERVAL", "20"))
# A threading.Event is used to signal the main loop to exit gracefully.
# This is a thread-safe way to manage shutdown requests from signal handlers.
_shutdown_event = Event()


def _handle_stop(signum: int, frame: object) -> None:  # pragma: no cover
    """
    A signal handler for graceful shutdown of the heartbeat process.

    This function is registered to handle `SIGTERM` (sent by Docker/Kubernetes
    to request a shutdown) and `SIGINT` (sent on Ctrl+C). When a signal is
    received, it logs a "stopping" message and sets the global `_shutdown_event`,
    which causes the main `_heartbeat_loop` to terminate cleanly.

    Args:
        signum: The number of the signal that was received.
        frame: The current stack frame (required by the signal handler signature).
    """

    log_event("INFO", "stopping", signal_received=signum)
    _shutdown_event.set()


def _register_signal_handlers() -> None:
    """Registers the `_handle_stop` function as the handler for SIGTERM and SIGINT."""
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)


def _heartbeat_loop() -> None:
    """
    The main loop that emits a periodic heartbeat log message.

    This loop will continue indefinitely until the `_shutdown_event` is set.
    It uses `_shutdown_event.wait()` with a timeout, which is an efficient way
    to sleep for the desired interval while still being immediately responsive
    to a shutdown signal.
    """
    while not _shutdown_event.is_set():
        log_event("INFO", "heartbeat", interval_seconds=_HEARTBEAT_INTERVAL)
        # Wait for the interval duration. If the shutdown event is set during
        # this time, the wait will be interrupted, and the loop will exit.
        if _shutdown_event.wait(timeout=_HEARTBEAT_INTERVAL):
            break


def main() -> int:
    """
    The main entrypoint for the worker's heartbeat process.

    This function orchestrates the lifecycle of the process:
    1.  Logs a detailed startup message, including a configuration summary.
    2.  Registers the signal handlers for graceful termination.
    3.  Enters the main heartbeat loop.
    4.  Logs a final "stopped" message when the loop terminates.

    Returns:
        An exit code of 0, indicating a clean and successful shutdown.
    """
    from heimdex_common.config import get_config

    config = get_config()
    log_event(
        "INFO",
        "starting_heartbeat",
        details={
            "interval_seconds": _HEARTBEART_INTERVAL,
            "config_summary": config.log_summary(redact_secrets=True),
        },
    )
    _register_signal_handlers()
    _heartbeat_loop()
    log_event("INFO", "stopped_heartbeat")
    return 0


if __name__ == "__main__":
    sys.exit(main())
