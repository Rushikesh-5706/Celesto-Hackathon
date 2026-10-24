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

from reprobox.sandbox.handle import GuestHandle

logger = logging.getLogger(__name__)


class ComputerRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active: dict[str, tuple[GuestHandle, Any]] = {}
        self._cleaning = False

    def register(self, handle: GuestHandle, provider: Any) -> None:
        with self._lock:
            self._active[handle.sandbox_name] = (handle, provider)
            logger.debug(
                "Registered sandbox %s (id=%s) in lifecycle registry",
                handle.sandbox_name,
                handle.computer_id,
            )

    def unregister(self, sandbox_name: str) -> None:
        with self._lock:
            self._active.pop(sandbox_name, None)

    def active_handles(self) -> list[GuestHandle]:
        with self._lock:
            return [h for h, _ in self._active.values()]

    def cleanup_all(self) -> None:
        with self._lock:
            if self._cleaning:
                return
            self._cleaning = True
            to_clean = list(self._active.items())

        for name, (handle, prov) in to_clean:
            try:
                logger.warning(
                    "Emergency cleanup deleting sandbox %s (id=%s)",
                    name,
                    handle.computer_id,
                )
                prov.delete(handle)
            except Exception as exc:
                logger.error("Failed emergency deletion of %s: %s", name, exc)
            finally:
                with self._lock:
                    self._active.pop(name, None)


registry = ComputerRegistry()
_handlers_installed = False


def _handle_exit_signal(signum: int, frame: Any) -> None:
    logger.warning("Received signal %d, cleaning up active computers", signum)
    registry.cleanup_all()
    sys.exit(128 + signum)


def install_cleanup_handlers() -> None:
    global _handlers_installed
    if _handlers_installed:
        return
    if threading.current_thread() is not threading.main_thread():
        logger.debug("Skipping signal handler installation: not main thread")
        return
    try:
        signal.signal(signal.SIGINT, _handle_exit_signal)
        signal.signal(signal.SIGTERM, _handle_exit_signal)
        atexit.register(registry.cleanup_all)
        _handlers_installed = True
        logger.debug("Cleanup signal handlers installed successfully")
    except (ValueError, AttributeError) as exc:
        logger.debug("Cannot install signal handlers: %s", exc)


@contextmanager
def managed_computer(
    provider: Any,
    name: str,
    max_delete_retries: int = 3,
) -> Generator[GuestHandle, None, None]:
    handle: GuestHandle | None = None
    try:
        handle = provider.create(name)
        registry.register(handle, provider)
    except Exception as exc:
        # Check if creation succeeded on cloud before raising
        created_id = getattr(handle, "computer_id", None)
        if not created_id:
            try:
                from reprobox.sandbox.celesto_provider import list_cloud_instances

                recent, _ = list_cloud_instances(limit=5)
                orphan_cids = [c["id"] for c in recent if c.get("id")]
                if orphan_cids:
                    logger.warning(
                        "Potential orphan computers found after creation failure: %s", orphan_cids
                    )
            except Exception as listing_err:
                logger.debug(
                    "Could not inspect cloud instances after creation error: %s", listing_err
                )
        raise exc

    try:
        yield handle
    finally:
        if handle is not None:
            deleted_ok = False
            last_err: Exception | None = None
            for attempt in range(1, max_delete_retries + 1):
                try:
                    provider.delete(handle)
                    deleted_ok = True
                    break
                except Exception as exc:
                    last_err = exc
                    time.sleep(1.0 * attempt)

            registry.unregister(name)
            if not deleted_ok:
                logger.error(
                    "Failed to delete computer %s (%s): %s", name, handle.computer_id, last_err
                )


def sweep_orphans(
    provider: Any,
    ledger_repo: Any = None,
    list_account: bool = False,
) -> list[str]:
    from reprobox.sandbox.celesto_provider import list_cloud_instances

    account_computers, _ = list_cloud_instances(limit=100)
    if list_account:
        print(f"Total computers in account: {len(account_computers)}")
        for comp in account_computers:
            print(f"- id={comp.get('id')} name={comp.get('name')} status={comp.get('status')}")
        return []

    # Get active project computer IDs from in-process registry and ledger
    project_cids = {h.computer_id for h in registry.active_handles()}
    if ledger_repo is not None:
        try:
            active_runs = ledger_repo.list_runs(limit=100)
            for r in active_runs:
                if r.get("state") not in ("deleted", "failed") and r.get("computer_id"):
                    project_cids.add(r["computer_id"])
        except Exception as exc:
            logger.warning("Could not query ledger for active runs during sweep: %s", exc)

    deleted: list[str] = []
    for comp in account_computers:
        cid = comp.get("id")
        if cid and cid in project_cids:
            logger.info("Sweeping project computer id=%s", cid)
            try:
                from celesto import CloudComputer

                CloudComputer.get(cid).delete()
                deleted.append(cid)
            except Exception as exc:
                logger.error("Failed to sweep computer %s: %s", cid, exc)

    return deleted
