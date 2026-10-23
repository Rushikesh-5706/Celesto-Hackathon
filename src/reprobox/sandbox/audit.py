"""Thread-safe append-only audit logger for command executions and file operations."""

from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path

from reprobox.constants import AUDIT_CMD_TRUNCATE, EXECUTION_TARGET
from reprobox.sandbox.naming import is_valid_sandbox_name
from reprobox.settings import settings


class AuditLogger:
    """Writes dual audit logs: commands.jsonl (contract) and audit_detail.jsonl (debug)."""

    def __init__(
        self,
        commands_path: Path | None = None,
        detail_path: Path | None = None,
    ) -> None:
        self.commands_path = commands_path or settings.audit_log_path
        self.detail_path = detail_path or (settings.logs_dir / "audit_detail.jsonl")
        self._lock = threading.Lock()

        # Ensure parent directories exist
        self.commands_path.parent.mkdir(parents=True, exist_ok=True)
        self.detail_path.parent.mkdir(parents=True, exist_ok=True)

    def _redact_secrets(self, text: str) -> str:
        """Strip known secret values from strings before logging."""
        secrets = [settings.celesto_api_key, settings.llm_api_key]
        sanitized = text
        for secret in secrets:
            if secret and len(secret) > 4:
                sanitized = sanitized.replace(secret, "[REDACTED_SECRET]")
        return sanitized

    def log_command(
        self,
        sandbox_name: str,
        command: str,
        decision: str,
        run_id: str = "",
        origin: str = "agent",
        step: str = "",
        rule_id: str = "",
        reason: str = "",
        exit_code: int | None = None,
        duration_s: float | None = None,
    ) -> None:
        """Log a command attempt according to the five-key contract and detail log."""
        if not is_valid_sandbox_name(sandbox_name):
            raise ValueError(f"Invalid sandbox name for audit log: {sandbox_name}")

        clean_cmd = command.strip()
        if not clean_cmd:
            clean_cmd = "[empty_command]"

        # Redact secrets
        clean_cmd = self._redact_secrets(clean_cmd)

        # Truncate if exceeds limit
        if len(clean_cmd) > AUDIT_CMD_TRUNCATE:
            clean_cmd = clean_cmd[:AUDIT_CMD_TRUNCATE] + "...[truncated]"

        ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        # Contract structure: exactly these 5 keys in this exact order
        cmd_record = {
            "ts": ts,
            "sandbox_name": sandbox_name,
            "command": clean_cmd,
            "decision": decision,
            "execution_target": EXECUTION_TARGET,
        }

        detail_record = {
            **cmd_record,
            "run_id": run_id,
            "origin": origin,
            "step": step,
            "rule_id": rule_id,
            "reason": reason,
            "exit_code": exit_code,
            "duration_s": duration_s,
        }

        cmd_line = json.dumps(cmd_record) + "\n"
        detail_line = json.dumps(detail_record) + "\n"

        with self._lock:
            with self.commands_path.open("a", encoding="utf-8") as f:
                f.write(cmd_line)
                f.flush()
                os.fsync(f.fileno())

            with self.detail_path.open("a", encoding="utf-8") as f:
                f.write(detail_line)
                f.flush()
                os.fsync(f.fileno())


# Module-level singleton
audit_logger = AuditLogger()
