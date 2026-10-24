from __future__ import annotations

import base64
import hashlib
import posixpath
import shlex
import time
from typing import Any

from reprobox.exceptions import CommandBlocked
from reprobox.sandbox.audit import AuditLogger
from reprobox.sandbox.guard import Guard
from reprobox.sandbox.handle import GuestHandle
from reprobox.sandbox.provider import RunResult


class AuditedProvider:
    """Audited provider wrapper that enforces security rules and logs before SDK calls."""

    CHUNK_SIZE = 48000

    def __init__(self, provider: Any, audit_logger: AuditLogger | None = None) -> None:
        self._provider = provider
        self.audit_logger = audit_logger or AuditLogger()

    def create(self, sandbox_name: str, **kwargs: Any) -> GuestHandle:
        t0 = time.monotonic()
        cmd_str = f"provision label={sandbox_name}"
        self.audit_logger.log_command(
            sandbox_name=sandbox_name,
            command=cmd_str,
            decision="allow",
            origin="pipeline",
            step="provision",
        )
        handle = self._provider.create(sandbox_name, **kwargs)
        elapsed = time.monotonic() - t0
        self.audit_logger.log_command(
            sandbox_name=sandbox_name,
            command=f"provision label={sandbox_name} computer_id={handle.computer_id}",
            decision="allow",
            origin="pipeline",
            step="provision",
            duration_s=elapsed,
        )
        return handle

    def run(
        self,
        guest: GuestHandle,
        command: str,
        origin: str = "agent",
        timeout: int = 60,
        step: str = "",
        run_id: str = "",
    ) -> RunResult:
        decision = Guard.evaluate(command, origin=origin)
        self.audit_logger.log_command(
            sandbox_name=guest.sandbox_name,
            command=command,
            decision="allow" if decision.allowed else "block",
            run_id=run_id,
            origin=origin,
            step=step,
            rule_id=decision.rule_id,
            reason=decision.reason,
        )

        if not decision.allowed:
            raise CommandBlocked(rule_id=decision.rule_id, reason=decision.reason, command=command)

        t0 = time.monotonic()
        res = self._provider.run(guest, command, timeout=timeout)
        elapsed = time.monotonic() - t0

        self.audit_logger.log_command(
            sandbox_name=guest.sandbox_name,
            command=command,
            decision="allow",
            run_id=run_id,
            origin=origin,
            step=step,
            rule_id=decision.rule_id,
            exit_code=res.exit_code,
            duration_s=elapsed,
        )
        return res

    def write_file(
        self,
        guest: GuestHandle,
        path: str,
        content: bytes,
        origin: str = "pipeline",
        step: str = "",
        run_id: str = "",
    ) -> None:
        norm_path = posixpath.normpath(path)
        if not norm_path.startswith("/workspace"):
            raise ValueError(f"Target path must be under /workspace: {path}")

        digest = hashlib.sha256(content).hexdigest()
        audit_cmd = f"write_file {norm_path} sha256={digest[:12]} bytes={len(content)}"
        self.audit_logger.log_command(
            sandbox_name=guest.sandbox_name,
            command=audit_cmd,
            decision="allow",
            run_id=run_id,
            origin=origin,
            step=step,
            rule_id="write_file_allow",
        )

        parent = posixpath.dirname(norm_path)
        mkdir_res = self._provider.run(guest, f"mkdir -p {parent}", timeout=30)
        if not mkdir_res.ok:
            raise RuntimeError(f"Failed to create directory {parent}: {mkdir_res.stderr}")

        b64_content = base64.b64encode(content).decode("ascii")
        chunks = [
            b64_content[i : i + self.CHUNK_SIZE]
            for i in range(0, len(b64_content), self.CHUNK_SIZE)
        ]

        if not chunks:
            # Empty file
            res = self._provider.run(guest, f"printf '' > {norm_path}", timeout=30)
            if not res.ok:
                raise RuntimeError(f"Failed to create empty file {norm_path}: {res.stderr}")
        else:
            for idx, chunk in enumerate(chunks):
                op = ">" if idx == 0 else ">>"
                cmd = f"printf %s '{chunk}' | base64 -d {op} {norm_path}"
                res = self._provider.run(guest, cmd, timeout=30)
                if not res.ok:
                    raise RuntimeError(f"Failed writing chunk {idx} to {norm_path}: {res.stderr}")

        check_res = self._provider.run(guest, f"sha256sum {norm_path}", timeout=30)
        if not check_res.ok:
            raise RuntimeError(f"Failed checking sha256 of {norm_path}: {check_res.stderr}")

        remote_hash = check_res.stdout.split()[0] if check_res.stdout else ""
        if remote_hash != digest:
            raise RuntimeError(
                f"Hash mismatch for {norm_path}: remote {remote_hash} != local {digest}"
            )

    def write_files(
        self,
        guest: GuestHandle,
        file_map: dict[str, bytes],
        origin: str = "pipeline",
        step: str = "",
        run_id: str = "",
    ) -> None:
        for path, data in file_map.items():
            self.write_file(guest, path, data, origin=origin, step=step, run_id=run_id)

    def read_file(
        self,
        guest: GuestHandle,
        path: str,
        origin: str = "agent",
        step: str = "",
        run_id: str = "",
    ) -> bytes:
        norm_path = posixpath.normpath(path)
        cmd_str = f"read_file {norm_path}"

        if Guard._is_secret_path(norm_path) or not norm_path.startswith("/workspace"):
            self.audit_logger.log_command(
                sandbox_name=guest.sandbox_name,
                command=cmd_str,
                decision="block",
                run_id=run_id,
                origin=origin,
                step=step,
                rule_id="secret_read",
                reason="Access to secret path prohibited",
            )
            raise CommandBlocked("secret_read", "Access to secret path prohibited", cmd_str)

        self.audit_logger.log_command(
            sandbox_name=guest.sandbox_name,
            command=cmd_str,
            decision="allow",
            run_id=run_id,
            origin=origin,
            step=step,
            rule_id="read_file_allow",
        )

        quoted = shlex.quote(norm_path)
        res = self._provider.run(guest, f"base64 -- {quoted}", timeout=30)
        if not res.ok:
            raise FileNotFoundError(f"File not found or unreadable: {norm_path} ({res.stderr})")

        return base64.b64decode(res.stdout.strip())

    def stop(
        self,
        guest: GuestHandle,
        origin: str = "pipeline",
        step: str = "",
        run_id: str = "",
    ) -> None:
        self.audit_logger.log_command(
            sandbox_name=guest.sandbox_name,
            command="stop",
            decision="allow",
            origin=origin,
            step=step,
            run_id=run_id,
        )
        self._provider.stop(guest)

    def start(
        self,
        guest: GuestHandle,
        origin: str = "pipeline",
        step: str = "",
        run_id: str = "",
    ) -> None:
        self.audit_logger.log_command(
            sandbox_name=guest.sandbox_name,
            command="start",
            decision="allow",
            origin=origin,
            step=step,
            run_id=run_id,
        )
        self._provider.start(guest)

    def resume(
        self,
        guest: GuestHandle,
        origin: str = "pipeline",
        step: str = "",
        run_id: str = "",
    ) -> None:
        self.audit_logger.log_command(
            sandbox_name=guest.sandbox_name,
            command="resume",
            decision="allow",
            origin=origin,
            step=step,
            run_id=run_id,
        )
        self._provider.resume(guest)

    def delete(
        self,
        guest: GuestHandle,
        origin: str = "pipeline",
        step: str = "",
        run_id: str = "",
    ) -> None:
        self.audit_logger.log_command(
            sandbox_name=guest.sandbox_name,
            command="delete",
            decision="allow",
            origin=origin,
            step=step,
            run_id=run_id,
        )
        self._provider.delete(guest)

    def publish_port(
        self,
        guest: GuestHandle,
        port: int,
        origin: str = "pipeline",
        step: str = "",
        run_id: str = "",
    ) -> Any:
        self.audit_logger.log_command(
            sandbox_name=guest.sandbox_name,
            command=f"publish_port {port}",
            decision="allow",
            origin=origin,
            step=step,
            run_id=run_id,
        )
        return self._provider.publish_port(guest, port)

    def unpublish_port(
        self,
        guest: GuestHandle,
        port: int,
        origin: str = "pipeline",
        step: str = "",
        run_id: str = "",
    ) -> Any:
        self.audit_logger.log_command(
            sandbox_name=guest.sandbox_name,
            command=f"unpublish_port {port}",
            decision="allow",
            origin=origin,
            step=step,
            run_id=run_id,
        )
        return self._provider.unpublish_port(guest, port)

    def exists(self, guest: GuestHandle) -> bool:
        return self._provider.exists(guest)
