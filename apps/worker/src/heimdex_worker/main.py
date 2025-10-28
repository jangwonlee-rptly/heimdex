"""Entrypoint for the Heimdex worker heartbeat process."""

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
    Handle termination signals gracefully.

    This function is registered as a signal handler for SIGTERM and SIGINT. It
    logs the received signal and sets a threading event to signal the main loop
    to exit.

    Args:
        signum: The signal number.
        frame: The current stack frame.
    """
    log_event("INFO", "stopping", signal=signum)
    _shutdown_event.set()


def _register_signal_handlers() -> None:
    """Register signal handlers for graceful shutdown."""
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)


def _heartbeat_loop() -> None:
    """
    Run the main heartbeat loop.

    This loop emits a "heartbeat" log message at a configured interval until the
    shutdown event is set by the signal handler.
    """
    while not _shutdown_event.is_set():
        log_event("INFO", "heartbeat", interval_seconds=_HEARTBEAT_INTERVAL)
        if _shutdown_event.wait(timeout=_HEARTBEAT_INTERVAL):
            break


def main() -> int:
    """
    Run the worker's main entrypoint.

    This function initializes the worker by logging a startup message, registering
    signal handlers for graceful shutdown, and starting the main heartbeat loop.

    Returns:
        An exit code of 0.
    """
    log_event("INFO", "starting", interval_seconds=_HEARTBEAT_INTERVAL)
    _register_signal_handlers()
    _heartbeat_loop()
    log_event("INFO", "stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
