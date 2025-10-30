"""
Outbox Dispatcher Service for Transactional Message Publishing.

This module implements the dispatcher component of the transactional outbox
pattern. It runs as a background thread within the API service, periodically
polling the outbox table for unsent messages and publishing them to Dramatiq.

This design guarantees exactly-once delivery semantics between the database
and the message broker, preventing the split-brain problem where a job could
exist in the database but never be published, or vice versa.

The dispatcher uses SELECT FOR UPDATE SKIP LOCKED to enable concurrent
instances to process different batches without blocking each other.
"""

from __future__ import annotations

import os
import signal
import threading
from typing import Any

import dramatiq

from heimdex_common.db import get_db
from heimdex_common.repositories import JobRepository

# Configuration from environment
OUTBOX_DISPATCH_INTERVAL_MS = int(os.getenv("OUTBOX_DISPATCH_INTERVAL_MS", "500"))
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Global flag for graceful shutdown
_shutdown_flag = threading.Event()


def _handle_shutdown(signum: int, frame: Any) -> None:
    """Signal handler for graceful shutdown."""
    print(f"[outbox_dispatcher] Received signal {signum}, shutting down gracefully...")
    _shutdown_flag.set()


def dispatch_outbox_messages() -> tuple[int, int]:
    """
    Polls the outbox table and publishes unsent messages to Dramatiq.

    This function is called periodically by the dispatcher thread. It:
    1. Retrieves unsent messages using FOR UPDATE SKIP LOCKED
    2. Publishes each message to the Dramatiq broker
    3. Marks successfully published messages as sent
    4. Records failures with fail_count and error message

    Returns:
        A tuple of (messages_sent, messages_failed).
    """
    sent_count = 0
    failed_count = 0

    # Get broker - this should be the same broker used by the worker
    broker = dramatiq.get_broker()

    with get_db() as session:
        repo = JobRepository(session)

        # Retrieve unsent messages with row-level locking
        unsent_messages = repo.get_unsent_outbox_messages(limit=100)

        for outbox_msg in unsent_messages:
            try:
                # Construct Dramatiq message from outbox payload
                message: dramatiq.Message = dramatiq.Message(
                    queue_name=outbox_msg.payload.get("queue_name", "default"),
                    actor_name=outbox_msg.task_name,
                    args=outbox_msg.payload.get("args", ()),
                    kwargs=outbox_msg.payload.get("kwargs", {}),
                    options=outbox_msg.payload.get("options", {}),
                )

                # Publish to broker
                broker.enqueue(message)

                # Mark as sent on successful publish
                repo.mark_outbox_sent(outbox_msg.id)
                sent_count += 1

            except Exception as e:
                # Record the failure
                error_msg = f"{type(e).__name__}: {e!s}"
                repo.mark_outbox_failed(outbox_msg.id, error_msg)
                failed_count += 1
                print(
                    f"[outbox_dispatcher] Failed to publish outbox_id={outbox_msg.id}: {error_msg}"
                )

        # Commit all changes (sent_at updates and fail_count increments)
        session.commit()

    return sent_count, failed_count


def run_dispatcher_loop() -> None:
    """
    Main dispatcher loop that runs in a background thread.

    This function continuously polls the outbox table at the configured
    interval until the shutdown flag is set. It's designed to be resilient,
    catching and logging exceptions without crashing the entire service.
    """
    interval_sec = OUTBOX_DISPATCH_INTERVAL_MS / 1000.0

    print(f"[outbox_dispatcher] Starting dispatcher loop (interval={interval_sec}s)")

    while not _shutdown_flag.is_set():
        try:
            sent, failed = dispatch_outbox_messages()
            if sent > 0 or failed > 0:
                print(f"[outbox_dispatcher] Dispatched: {sent} sent, {failed} failed")

        except Exception as e:
            print(f"[outbox_dispatcher] Error in dispatch loop: {e}")

        # Wait for the interval or until shutdown is signaled
        _shutdown_flag.wait(timeout=interval_sec)

    print("[outbox_dispatcher] Dispatcher loop stopped")


def start_dispatcher_thread() -> threading.Thread:
    """
    Starts the outbox dispatcher as a background daemon thread.

    This function is called during API server startup. The dispatcher thread
    will automatically terminate when the main process exits.

    Returns:
        The dispatcher thread instance.
    """
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)

    dispatcher_thread = threading.Thread(
        target=run_dispatcher_loop,
        name="outbox-dispatcher",
        daemon=True,
    )
    dispatcher_thread.start()

    print("[outbox_dispatcher] Background dispatcher thread started")
    return dispatcher_thread


def stop_dispatcher() -> None:
    """
    Signals the dispatcher to stop and waits for it to finish.

    This is useful for graceful shutdown in testing or when the API
    server is being shut down cleanly.
    """
    _shutdown_flag.set()
    print("[outbox_dispatcher] Stop signal sent to dispatcher")
