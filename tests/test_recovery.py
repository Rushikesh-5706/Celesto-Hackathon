from __future__ import annotations

import hashlib

import pytest

from reprobox.exceptions import PolicyUnavailable
from reprobox.pipeline.recovery import RecoveryHandler
from reprobox.sandbox.handle import GuestHandle
from reprobox.sandbox.provider import RunResult


class MockAuditedProvider:
    def __init__(self, test_content: bytes = b"test", can_resume: bool = True) -> None:
        self.test_content = test_content
        self.can_resume = can_resume
        self.resumed = False
        self.created_handles: list[GuestHandle] = []
        self.files_written: dict[str, bytes] = {}

    def create(self, name: str) -> GuestHandle:
        handle = GuestHandle(sandbox_name=name, computer_id=f"cmp_{name}", sdk_object=None)
        self.created_handles.append(handle)
        return handle

    def resume(self, handle: GuestHandle, **kwargs) -> None:
        if not self.can_resume:
            raise RuntimeError("Simulation: unrecoverable resume error")
        self.resumed = True

    def run(self, handle: GuestHandle, command: str, **kwargs) -> RunResult:
        if not self.can_resume and "python3 --version" in command:
            return RunResult(
                stdout="", stderr="Unready", exit_code=1, computer_id=handle.computer_id
            )
        return RunResult(
            stdout="Python 3.12", stderr="", exit_code=0, computer_id=handle.computer_id
        )

    def read_file(self, handle: GuestHandle, path: str, **kwargs) -> bytes:
        return self.test_content

    def write_file(self, handle: GuestHandle, path: str, content: bytes, **kwargs) -> None:
        self.files_written[path] = content


def test_recovery_resume_succeeds():
    events = []
    test_bytes = b"def test_foo(): assert False\n"
    test_sha = hashlib.sha256(test_bytes).hexdigest()
    prov = MockAuditedProvider(test_content=test_bytes)
    handle = GuestHandle("sbx-orig12345", "cmp_orig", None)

    handler = RecoveryHandler(
        provider=prov,
        computer=handle,
        sandbox_name="sbx-orig12345",
        run_id="run-recov1",
        checkpoint_test_bytes=test_bytes,
        checkpoint_test_sha=test_sha,
        checkpoint_manifest={},
        event_callback=lambda ev, payload: events.append((ev, payload)),
    )

    result = handler.handle_step7_failure(
        step7_executor=lambda c: (True, "test failed as expected", "")
    )

    assert result.recovered is True
    assert result.policy_applied == "resume"
    assert any(ev[0] == "policy_selected" and ev[1]["policy"] == "resume" for ev in events)
    assert any(ev[0] == "policy_applied" and ev[1]["policy"] == "resume" for ev in events)


def test_recovery_fresh_fallback_on_integrity_failure():
    events = []
    original_bytes = b"original"
    corrupted_bytes = b"corrupted"
    prov = MockAuditedProvider(test_content=corrupted_bytes)
    handle = GuestHandle("sbx-orig12345", "cmp_orig", None)

    replayed = False

    def replay_callback(h):
        nonlocal replayed
        replayed = True

    handler = RecoveryHandler(
        provider=prov,
        computer=handle,
        sandbox_name="sbx-orig12345",
        run_id="run-recov2",
        checkpoint_test_bytes=original_bytes,
        checkpoint_test_sha=hashlib.sha256(original_bytes).hexdigest(),
        checkpoint_manifest={},
        event_callback=lambda ev, payload: events.append((ev, payload)),
    )

    result = handler.handle_step7_failure(
        step7_executor=lambda c: (True, "recovered in fresh", ""),
        stage_replay_callback=replay_callback,
    )

    assert result.recovered is True
    assert result.policy_applied == "fresh"
    assert result.fallback_sandbox_name is not None
    assert replayed is True
    assert any(ev[0] == "policy_escalated" for ev in events)
    assert any(ev[0] == "policy_applied" and ev[1]["policy"] == "fresh" for ev in events)


def test_recovery_rollback_raises_policy_unavailable():
    prov = MockAuditedProvider()
    handle = GuestHandle("sbx-orig12345", "cmp_orig", None)
    handler = RecoveryHandler(
        provider=prov,
        computer=handle,
        sandbox_name="sbx-orig12345",
        run_id="run-recov3",
        checkpoint_test_bytes=b"",
        checkpoint_test_sha="",
        checkpoint_manifest={},
        event_callback=lambda ev, payload: None,
    )

    with pytest.raises(PolicyUnavailable) as exc_info:
        handler.rollback()
    assert "snapshot" in str(exc_info.value).lower() or "rollback" in str(exc_info.value).lower()
