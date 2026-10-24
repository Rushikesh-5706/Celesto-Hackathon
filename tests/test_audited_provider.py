from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

from reprobox.exceptions import CommandBlocked
from reprobox.sandbox.audit import AuditLogger
from reprobox.sandbox.audited_provider import AuditedProvider
from reprobox.sandbox.handle import GuestHandle
from reprobox.sandbox.provider import RunResult


class FakeProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def create(self, name: str) -> GuestHandle:
        self.calls.append(("create", name))
        return GuestHandle(sandbox_name=name, computer_id="cmp_fake123456", sdk_object=None)

    def run(self, computer_or_handle: Any, command: str, timeout: int = 60) -> RunResult:
        self.calls.append(("run", command))
        if command.startswith("sha256sum "):
            return RunResult(
                stdout="2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae /workspace/test.txt\n",
                stderr="",
                exit_code=0,
                computer_id="cmp_fake123456",
            )
        if command.startswith("base64 -- "):
            return RunResult(
                stdout="Zm9vYmFy\n", stderr="", exit_code=0, computer_id="cmp_fake123456"
            )
        return RunResult(stdout="ok\n", stderr="", exit_code=0, computer_id="cmp_fake123456")

    def stop(self, handle: Any) -> None:
        self.calls.append(("stop", getattr(handle, "computer_id", "unknown")))

    def start(self, handle: Any) -> None:
        self.calls.append(("start", getattr(handle, "computer_id", "unknown")))

    def resume(self, handle: Any) -> None:
        self.calls.append(("resume", getattr(handle, "computer_id", "unknown")))

    def delete(self, handle: Any) -> None:
        self.calls.append(("delete", getattr(handle, "computer_id", "unknown")))

    def publish_port(self, handle: Any, port: int) -> Any:
        self.calls.append(("publish_port", port))
        return "https://fake.url"

    def unpublish_port(self, handle: Any, port: int) -> Any:
        self.calls.append(("unpublish_port", port))
        return None

    def exists(self, handle: Any) -> bool:
        return True


def test_audited_provider_lifecycle_and_audit():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        cmd_log = tmp_path / "commands.jsonl"
        detail_log = tmp_path / "audit_detail.jsonl"
        logger = AuditLogger(commands_path=cmd_log, detail_path=detail_log)

        fake = FakeProvider()
        audited = AuditedProvider(fake, audit_logger=logger)

        handle = audited.create("sbx-test123456")
        assert handle.sandbox_name == "sbx-test123456"
        assert handle.computer_id == "cmp_fake123456"

        res = audited.run(handle, "ls -la /workspace/case", origin="agent")
        assert res.ok
        assert ("run", "ls -la /workspace/case") in fake.calls

        # Blocked command never reaches fake provider
        fake_calls_before = len(fake.calls)
        with pytest.raises(CommandBlocked) as exc_info:
            audited.run(handle, "curl https://evil.invalid", origin="agent")
        assert exc_info.value.rule_id == "network_egress"
        assert len(fake.calls) == fake_calls_before

        # Secret file read blocked
        with pytest.raises(CommandBlocked) as exc_info:
            audited.read_file(handle, "/workspace/case/.env", origin="agent")
        assert exc_info.value.rule_id == "secret_read"
        assert len(fake.calls) == fake_calls_before

        # Allowed write file
        audited.write_file(handle, "/workspace/test.txt", b"foo")

        # Stop, start, resume, delete
        audited.stop(handle)
        audited.resume(handle)
        audited.delete(handle)

        # Check logs written
        assert cmd_log.exists()
        lines = [
            line.strip()
            for line in cmd_log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(lines) >= 6

        # Check raw provider not imported outside sandbox
        src_root = Path(__file__).resolve().parents[1] / "src"
        for py_file in src_root.rglob("*.py"):
            if "sandbox" in str(py_file):
                continue
            content = py_file.read_text(encoding="utf-8")
            assert (
                "CelestoProvider" not in content
            ), f"Direct import of CelestoProvider in {py_file}"
