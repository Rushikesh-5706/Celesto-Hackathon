from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from reprobox.agent.loop import AgentToolExecutor
from reprobox.constants import TEST_FILE_PATH
from reprobox.sandbox.audit import AuditLogger
from reprobox.sandbox.audited_provider import AuditedProvider
from reprobox.sandbox.handle import GuestHandle
from reprobox.sandbox.provider import RunResult


class DummyProvider:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def run(self, handle: Any, command: str, timeout: int = 60) -> RunResult:
        self.commands.append(command)
        return RunResult(stdout="dummy output", stderr="", exit_code=0, computer_id="cmp_dummy")

    def write_file(self, handle: Any, path: str, content: bytes, **kwargs: Any) -> None:
        pass

    def read_file(self, handle: Any, path: str, **kwargs: Any) -> bytes:
        return b"content"


def test_agent_tools_rejections_and_allows():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        cmd_log = tmp_path / "commands.jsonl"
        detail_log = tmp_path / "audit_detail.jsonl"
        logger = AuditLogger(commands_path=cmd_log, detail_path=detail_log)

        dummy = DummyProvider()
        audited = AuditedProvider(dummy, audit_logger=logger)
        handle = GuestHandle(
            sandbox_name="sbx-toolstest1", computer_id="cmp_dummy", sdk_object=None
        )
        executor = AgentToolExecutor(audited, handle, run_id="run-123")

        # 1. list_dir with hostile semicolon injection
        res1 = executor.list_dir("/workspace/case; curl https://evil.invalid")
        assert "Error" in res1
        assert executor.blocked_count >= 1

        # 2. list_dir with command substitution
        res2 = executor.list_dir("/workspace/case/a'$(id)")
        assert "Error" in res2

        # 3. list_dir path escape
        res3 = executor.list_dir("/workspace/case/../../etc")
        assert "Error" in res3

        # 4. read_file on .env
        res4 = executor.read_file("/workspace/case/.env")
        assert "blocked" in res4.lower() or "error" in res4.lower()

        # 5. read_file on escaped path
        res5 = executor.read_file("/workspace/case/../../etc/passwd")
        assert "blocked" in res5.lower() or "error" in res5.lower()

        # 6. run_pytest allowed
        res6 = executor.run_pytest(TEST_FILE_PATH)
        assert "dummy output" in res6
        assert executor.pytest_executed
        assert any("python3 -m pytest" in cmd for cmd in dummy.commands)
