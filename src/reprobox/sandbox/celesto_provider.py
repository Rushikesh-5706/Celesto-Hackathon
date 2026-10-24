from __future__ import annotations

import logging
import os
import time
from typing import Any

from reprobox.sandbox.handle import GuestHandle
from reprobox.sandbox.provider import ComputerProvider, RunResult
from reprobox.settings import settings

logger = logging.getLogger(__name__)


def list_cloud_instances(limit: int = 50) -> tuple[list[dict[str, Any]], bool]:
    # Celesto SDK 0.1.8 does not expose a public Computer.list() method,
    # so we wrap the internal cloud listing function.
    from celesto._providers.cloud import list_cloud_computers

    return list_cloud_computers(limit=limit)


class CelestoProvider(ComputerProvider):
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.celesto_api_key or os.environ.get("CELESTO_API_KEY", "")
        if self.api_key and not os.environ.get("CELESTO_API_KEY"):
            os.environ["CELESTO_API_KEY"] = self.api_key

    def _ensure_sdk(self) -> Any:
        try:
            from celesto import Computer

            return Computer
        except ImportError as exc:
            raise RuntimeError("Celesto SDK is not installed or import failed") from exc

    def create(self, name: str) -> GuestHandle:
        computer_cls = self._ensure_sdk()
        kwargs: dict[str, Any] = {"provider": "cloud"}
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if settings.celesto_template_id:
            kwargs["template_id"] = settings.celesto_template_id
        computer = computer_cls(**kwargs)
        computer.start()
        cid = getattr(computer, "id", "unknown")
        logger.info("Celesto computer started with id=%s (sandbox=%s)", cid, name)
        return GuestHandle(sandbox_name=name, computer_id=cid, sdk_object=computer)

    def run(self, computer_or_handle: Any, command: str, timeout: int = 60) -> RunResult:
        computer = (
            computer_or_handle.sdk_object
            if isinstance(computer_or_handle, GuestHandle)
            else computer_or_handle
        )
        cid = getattr(computer_or_handle, "computer_id", getattr(computer, "id", "unknown"))

        max_attempts = 4
        transient_indicators = (
            "409",
            "conflict",
            "busy",
            "readtimeout",
            "connecttimeout",
            "timeout",
            "operation error",
            "502",
            "503",
            "504",
            "connection reset",
            "protocol",
        )
        for attempt in range(max_attempts):
            t0 = time.monotonic()
            try:
                res = computer.run(command, timeout=timeout)
                elapsed = time.monotonic() - t0
                return RunResult(
                    stdout=res.stdout or "",
                    stderr=res.stderr or "",
                    exit_code=res.exit_code,
                    computer_id=cid,
                    elapsed_s=elapsed,
                )
            except Exception as exc:
                err_msg = str(exc).lower()
                is_transient = any(ind in err_msg for ind in transient_indicators)
                if is_transient and attempt < max_attempts - 1:
                    wait_s = 2.0 * (attempt + 1)
                    logger.warning(
                        "Transient Celesto error (%s), retrying in %.1fs (attempt %d/%d)...",
                        exc,
                        wait_s,
                        attempt + 1,
                        max_attempts,
                    )
                    time.sleep(wait_s)
                    continue
                raise

    def stop(self, computer_or_handle: Any) -> None:
        computer = (
            computer_or_handle.sdk_object
            if isinstance(computer_or_handle, GuestHandle)
            else computer_or_handle
        )
        cid = getattr(computer_or_handle, "computer_id", getattr(computer, "id", "unknown"))
        logger.info("Stopping Celesto computer id=%s", cid)
        computer.stop()

    def start(self, computer_or_handle: Any) -> None:
        computer = (
            computer_or_handle.sdk_object
            if isinstance(computer_or_handle, GuestHandle)
            else computer_or_handle
        )
        cid = getattr(computer_or_handle, "computer_id", getattr(computer, "id", "unknown"))
        logger.info("Starting/resuming Celesto computer id=%s", cid)
        if hasattr(computer, "resume"):
            try:
                computer.resume()
                return
            except Exception as resume_err:
                logger.debug("Resume call fell back to start: %s", resume_err)
        computer.start()

    def resume(self, computer_or_handle: Any) -> None:
        computer = (
            computer_or_handle.sdk_object
            if isinstance(computer_or_handle, GuestHandle)
            else computer_or_handle
        )
        cid = getattr(computer_or_handle, "computer_id", getattr(computer, "id", "unknown"))
        logger.info("Resuming Celesto computer id=%s", cid)
        if hasattr(computer, "resume"):
            computer.resume()
        else:
            computer.start()

    def delete(self, computer_or_handle: Any) -> None:
        computer = (
            computer_or_handle.sdk_object
            if isinstance(computer_or_handle, GuestHandle)
            else computer_or_handle
        )
        cid = getattr(computer_or_handle, "computer_id", getattr(computer, "id", "unknown"))
        logger.info("Deleting Celesto computer id=%s", cid)
        computer.delete()

    def publish_port(self, computer_or_handle: Any, port: int) -> Any:
        computer = (
            computer_or_handle.sdk_object
            if isinstance(computer_or_handle, GuestHandle)
            else computer_or_handle
        )
        return computer.publish_port(port)

    def unpublish_port(self, computer_or_handle: Any, port: int) -> Any:
        computer = (
            computer_or_handle.sdk_object
            if isinstance(computer_or_handle, GuestHandle)
            else computer_or_handle
        )
        return computer.unpublish_port(port)

    def exists(self, computer_or_handle: Any) -> bool:
        computer = (
            computer_or_handle.sdk_object
            if isinstance(computer_or_handle, GuestHandle)
            else computer_or_handle
        )
        try:
            res = self.run(computer, "echo ping", timeout=10)
            return res.ok
        except Exception:
            return False
