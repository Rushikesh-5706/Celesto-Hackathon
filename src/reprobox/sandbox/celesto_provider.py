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
        import os

        self.api_key = api_key or settings.celesto_api_key or os.environ.get("CELESTO_API_KEY", "")
        if self.api_key and not os.environ.get("CELESTO_API_KEY"):
            os.environ["CELESTO_API_KEY"] = self.api_key

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
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if settings.celesto_template_id:
            kwargs["template_id"] = settings.celesto_template_id
        computer = computer_cls(**kwargs)
        computer.start()
        computer._sandbox_name = name
        logger.info("Celesto computer started with id=%s (sandbox=%s)", computer.id, name)
        return computer

    def run(self, computer: Any, command: str, timeout: int = 60) -> RunResult:
        """Execute a shell command inside the computer sandbox with retry on transient network/API errors."""
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
                    computer_id=getattr(computer, "id", "unknown"),
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

    def write_files(self, computer: Any, file_map: dict[str, bytes]) -> None:
        """Write multiple binary files to the sandbox in a single batched run."""
        if not file_map:
            return
        import json

        encoded = {path: base64.b64encode(data).decode("ascii") for path, data in file_map.items()}
        payload = json.dumps(encoded)
        b64_payload = base64.b64encode(payload.encode("utf-8")).decode("ascii")
        guest_code = (
            "import base64, json, pathlib\n"
            f"payload = json.loads(base64.b64decode('{b64_payload}').decode('utf-8'))\n"
            "for p_str, b64_bytes in payload.items():\n"
            "    p = pathlib.Path(p_str)\n"
            "    p.parent.mkdir(parents=True, exist_ok=True)\n"
            "    p.write_bytes(base64.b64decode(b64_bytes))\n"
        )
        b64_script = base64.b64encode(guest_code.encode("utf-8")).decode("ascii")
        res = self.run(
            computer,
            f"python3 -c \"import base64; exec(base64.b64decode('{b64_script}').decode())\"",
        )
        if res.exit_code != 0:
            raise RuntimeError(f"Failed to batch write files: {res.stderr}")

    def write_file(self, computer: Any, path: str, data: bytes) -> None:
        """Write binary data to an absolute path inside the sandbox."""
        self.write_files(computer, {path: data})

    def read_file(self, computer: Any, path: str) -> bytes:
        """Read binary data from an absolute path inside the sandbox."""
        res = self.run(computer, f"base64 {path!r}")
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
