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
    log_event("INFO", "stopping", signal=signum)
    _shutdown_event.set()


def _register_signal_handlers() -> None:
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)


def _heartbeat_loop() -> None:
    while not _shutdown_event.is_set():
        log_event("INFO", "heartbeat", interval_seconds=_HEARTBEAT_INTERVAL)
        if _shutdown_event.wait(timeout=_HEARTBEAT_INTERVAL):
            break


def main() -> int:
    log_event("INFO", "starting", interval_seconds=_HEARTBEAT_INTERVAL)
    _register_signal_handlers()
    _heartbeat_loop()
    log_event("INFO", "stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
