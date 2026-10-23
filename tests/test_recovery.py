"""Unit tests for Step 7 failure recovery branches."""

import hashlib

from reprobox.pipeline.recovery import RecoveryHandler


class FakeRecoveryProvider:
    def __init__(self, test_content: bytes = b"test") -> None:
        self.started = False
        self.test_content = test_content

    def start(self, comp) -> None:
        self.started = True

    def run(self, comp, cmd, timeout=60):
        from reprobox.sandbox.provider import RunResult
        return RunResult(stdout="Python 3.12", stderr="", exit_code=0, computer_id="c1")

    def read_file(self, comp, path):
        return self.test_content


def test_recovery_resume_succeeds():
    events = []
    test_bytes = b"def test_foo(): assert False\n"
    test_sha = hashlib.sha256(test_bytes).hexdigest()
    prov = FakeRecoveryProvider(test_content=test_bytes)

    handler = RecoveryHandler(
        provider=prov,
        computer=None,
        sandbox_name="sbx-recovtest1",
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


def test_recovery_escalates_on_integrity_failure():
    events = []
    original_bytes = b"original"
    corrupted_bytes = b"corrupted_content"
    prov = FakeRecoveryProvider(test_content=corrupted_bytes)

    handler = RecoveryHandler(
        provider=prov,
        computer=None,
        sandbox_name="sbx-recovtest2",
        run_id="run-recov2",
        checkpoint_test_bytes=original_bytes,
        checkpoint_test_sha=hashlib.sha256(original_bytes).hexdigest(),
        checkpoint_manifest={},
        event_callback=lambda ev, payload: events.append((ev, payload)),
    )

    result = handler.handle_step7_failure(
        step7_executor=lambda c: (True, "", "")
    )

    assert result.recovered is False
    assert result.policy_applied == "fresh_required"
    assert any(ev[0] == "policy_escalated" for ev in events)
