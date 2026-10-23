"""Sandbox lifecycle hygiene: managed context manager, process registry, signal handling, and orphan sweep."""

from __future__ import annotations

import atexit
import logging
import signal
import sys
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from reprobox.sandbox.provider import ComputerProvider

logger = logging.getLogger(__name__)


class ComputerRegistry:
    """Process-wide registry tracking active sandboxes for fail-safe cleanup."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active: dict[str, tuple[Any, ComputerProvider]] = {}
        self._cleaning = False

    def register(self, sandbox_name: str, computer: Any, provider: ComputerProvider) -> None:
        with self._lock:
            self._active[sandbox_name] = (computer, provider)
            logger.debug(
                "Registered sandbox %s in lifecycle registry (active=%d)",
                sandbox_name,
                len(self._active),
            )

    def unregister(self, sandbox_name: str) -> None:
        with self._lock:
            self._active.pop(sandbox_name, None)
            logger.debug("Unregistered sandbox %s from lifecycle registry", sandbox_name)

    def active_names(self) -> list[str]:
        with self._lock:
            return list(self._active.keys())

    def cleanup_all(self) -> None:
        """Emergency cleanup of all tracked computers."""
        with self._lock:
            if self._cleaning:
                return
            self._cleaning = True
            to_clean = list(self._active.items())

        for name, (comp, prov) in to_clean:
            try:
                logger.warning(
                    "Emergency cleanup: deleting sandbox %s (id=%s)...",
                    name,
                    getattr(comp, "id", None),
                )
                prov.delete(comp)
            except Exception as exc:
                logger.error("Failed emergency deletion of %s: %s", name, exc)
            finally:
                with self._lock:
                    self._active.pop(name, None)


# Global registry singleton
registry = ComputerRegistry()


def _handle_exit_signal(signum: int, frame: Any) -> None:
    logger.warning("Received signal %d, cleaning up active computers...", signum)
    registry.cleanup_all()
    sys.exit(128 + signum)


# Install handlers once
signal.signal(signal.SIGINT, _handle_exit_signal)
signal.signal(signal.SIGTERM, _handle_exit_signal)
atexit.register(registry.cleanup_all)


@contextmanager
def managed_computer(
    provider: ComputerProvider,
    name: str,
    max_delete_retries: int = 3,
) -> Generator[Any, None, None]:
    """Single context manager for computer lifecycle ensuring deterministic deletion."""
    computer = provider.create(name)
    registry.register(name, computer, provider)

    try:
        yield computer
    finally:
        deletion_confirmed = False
        last_error: Exception | None = None

        for attempt in range(1, max_delete_retries + 1):
            try:
                logger.info(
                    "Deleting computer for sandbox %s (attempt %d/%d)...",
                    name,
                    attempt,
                    max_delete_retries,
                )
                provider.delete(computer)
                # Confirm deletion if supported
                if not provider.exists(computer):
                    deletion_confirmed = True
                    break
                logger.warning(
                    "Sandbox %s still exists after delete attempt %d, retrying...", name, attempt
                )
                time.sleep(2.0 * attempt)
            except Exception as exc:
                last_error = exc
                logger.warning("Delete attempt %d failed for %s: %s", attempt, name, exc)
                time.sleep(2.0 * attempt)

        registry.unregister(name)

        if not deletion_confirmed and provider.exists(computer):
            msg = f"CRITICAL: Failed to confirm deletion of sandbox {name} after {max_delete_retries} attempts: {last_error}"
            logger.error(msg)
            raise RuntimeError(msg)


def sweep_orphans(provider: ComputerProvider) -> list[str]:
    """Identify and delete any leftover sandbox computers."""
    logger.info("Running orphan sweep...")
    active_ids = provider.list_prefixed()
    deleted: list[str] = []

    # If provider is CelestoProvider, use Computer.get or direct deletion
    for cid in active_ids:
        logger.info("Sweeping orphan computer id=%s", cid)
        try:
            from celesto import Computer

            comp = Computer.get(cid)
            comp.delete()
            deleted.append(cid)
        except Exception as exc:
            logger.error("Failed to sweep computer %s: %s", cid, exc)

    logger.info("Sweep complete. Deleted %d orphans.", len(deleted))
    return deleted
