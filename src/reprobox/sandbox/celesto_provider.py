"""Celesto Cloud sandbox provider implementation using the official Python SDK."""

from __future__ import annotations

import base64
import logging
import time
from typing import Any

from reprobox.sandbox.provider import ComputerProvider, RunResult
from reprobox.settings import settings

logger = logging.getLogger(__name__)


class CelestoProvider(ComputerProvider):
    """Production provider using Celesto Cloud."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.celesto_api_key

    def _ensure_sdk(self) -> Any:
        try:
            from celesto import Computer
            return Computer
        except ImportError as exc:
            raise RuntimeError("Celesto SDK is not installed or import failed") from exc

    def create(self, name: str) -> Any:
        """Create and start a cloud computer sandbox."""
        computer_cls = self._ensure_sdk()
        kwargs: dict[str, Any] = {"provider": "cloud"}
        if settings.celesto_template_id:
            kwargs["template_id"] = settings.celesto_template_id
        computer = computer_cls(**kwargs)
        computer.start()
        computer._sandbox_name = name
        logger.info("Celesto computer started with id=%s (sandbox=%s)", computer.id, name)
        return computer

    def run(self, computer: Any, command: str, timeout: int = 60) -> RunResult:
        """Execute a shell command inside the computer sandbox."""
        t0 = time.monotonic()
        res = computer.run(command, timeout=timeout)
        elapsed = time.monotonic() - t0
        return RunResult(
            stdout=res.stdout or "",
            stderr=res.stderr or "",
            exit_code=res.exit_code,
            computer_id=getattr(computer, "id", "unknown"),
            elapsed_s=elapsed,
        )

    def write_file(self, computer: Any, path: str, data: bytes) -> None:
        """Write binary data to an absolute path inside the sandbox."""
        b64_str = base64.b64encode(data).decode("ascii")
        # Ensure parent directory exists and decode data
        script = (
            f"import base64, pathlib\n"
            f"p = pathlib.Path({path!r})\n"
            f"p.parent.mkdir(parents=True, exist_ok=True)\n"
            f"p.write_bytes(base64.b64decode({b64_str!r}))\n"
        )
        b64_script = base64.b64encode(script.encode("utf-8")).decode("ascii")
        res = computer.run(f"python3 -c \"import base64; exec(base64.b64decode('{b64_script}').decode())\"")
        if res.exit_code != 0:
            raise RuntimeError(f"Failed to write file {path}: {res.stderr}")

    def read_file(self, computer: Any, path: str) -> bytes:
        """Read binary data from an absolute path inside the sandbox."""
        res = computer.run(f"base64 {path!r}")
        if res.exit_code != 0:
            raise FileNotFoundError(f"File {path} not found or unreadable: {res.stderr}")
        return base64.b64decode(res.stdout)

    def stop(self, computer: Any) -> None:
        """Stop the sandbox computer."""
        logger.info("Stopping Celesto computer id=%s", computer.id)
        computer.stop()

    def start(self, computer: Any) -> None:
        """Start or resume the stopped sandbox computer."""
        logger.info("Starting Celesto computer id=%s", computer.id)
        computer.start()

    def delete(self, computer: Any) -> None:
        """Delete the sandbox computer."""
        logger.info("Deleting Celesto computer id=%s", getattr(computer, "id", None))
        computer.delete()

    def exists(self, computer: Any) -> bool:
        """Check if computer exists in cloud active list."""
        from celesto._providers.cloud import list_cloud_computers
        cid = getattr(computer, "id", "")
        if not cid:
            return False
        items, _ = list_cloud_computers()
        return any(item.get("id") == cid for item in items)

    def list_prefixed(self, prefix: str = "") -> list[str]:
        """List active computer ids."""
        from celesto._providers.cloud import list_cloud_computers
        items, _ = list_cloud_computers()
        return [str(item["id"]) for item in items if str(item.get("id", "")).startswith(prefix)]
