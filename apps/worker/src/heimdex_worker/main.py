"""
Entrypoint for the Heimdex Worker Heartbeat Process.

This module provides a simple heartbeat process for the worker service. It
emits a periodic log message to indicate that the worker is alive and running.
This is useful for monitoring and ensuring that the worker container is healthy.

The main process is designed to be lightweight and does not handle any actual
job processing. Job processing is handled by the Dramatiq actors in `tasks.py`,
which are run in a separate process by the Dramatiq CLI.
"""

from __future__ import annotations

import os
import signal
import sys
from threading import Event

from .logger import log_event

_HEARTBEAT_INTERVAL = int(os.getenv("HEIMDEX_HEARTBEAT_INTERVAL", "20"))
_shutdown_event = Event()


def _handle_stop(signum: int, frame: object) -> None:  # pragma: no cover - signal handler
    """
    Handles termination signals gracefully.

    This function is registered as a signal handler for `SIGTERM` and `SIGINT`.
    When a termination signal is received, it logs a 'stopping' message and
    sets a `threading.Event` to signal the main heartbeat loop to exit
    cleanly.

    Args:
        signum (int): The signal number that was received.
        frame (object): The current stack frame. This argument is required by
            the `signal` module but is not used in this function.
    """
    log_event("INFO", "stopping", signal=signum)
    _shutdown_event.set()


def _register_signal_handlers() -> None:
    """
    Registers signal handlers for graceful shutdown.

    This function sets up handlers for `SIGTERM` and `SIGINT` to ensure that
    the worker process can be terminated gracefully.
    """
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)


def _heartbeat_loop() -> None:
    """
    Runs the main heartbeat loop.

    This loop emits a periodic 'heartbeat' log message at a configured
    interval (`HEIMDEX_HEARTBEAT_INTERVAL`). It continues to run until the
    shutdown event is set by the signal handler. The use of `_shutdown_event.wait`
    ensures that the loop exits promptly when a shutdown is requested.
    """
    while not _shutdown_event.is_set():
        log_event("INFO", "heartbeat", interval_seconds=_HEARTBEAT_INTERVAL)
        if _shutdown_event.wait(timeout=_HEARTBEAT_INTERVAL):
            break


def main() -> int:
    """
    Runs the worker's main entrypoint.

    This function serves as the main entrypoint for the worker's heartbeat
    process. It performs the following steps:
    1.  Logs a startup message with redacted configuration.
    2.  Registers signal handlers for graceful shutdown.
    3.  Starts the main heartbeat loop.
    4.  Logs a final 'stopped' message upon exiting the loop.

    Returns:
        int: An exit code of 0 to indicate successful execution.
    """
    from heimdex_common.config import get_config

    config = get_config()
    log_event(
        "INFO",
        "starting",
        interval_seconds=_HEARTBEAT_INTERVAL,
        config=config.log_summary(redact_secrets=True),
    )
    _register_signal_handlers()
    _heartbeat_loop()
    log_event("INFO", "stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
