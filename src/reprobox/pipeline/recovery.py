from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from reprobox.constants import FAILURE_POLICY, RESUME_MAX_ATTEMPTS, TEST_FILE_PATH
from reprobox.exceptions import PolicyUnavailable
from reprobox.sandbox.audited_provider import AuditedProvider
from reprobox.sandbox.handle import GuestHandle
from reprobox.sandbox.naming import new_sandbox_name

logger = logging.getLogger(__name__)


@dataclass
class RecoveryResult:
    recovered: bool
    policy_applied: str
    attempts: int
    resume_ready_s: float
    fallback_computer: GuestHandle | None = None
    fallback_sandbox_name: str | None = None
    error: str | None = None


class RecoveryHandler:
    def __init__(
        self,
        provider: AuditedProvider,
        computer: GuestHandle,
        sandbox_name: str,
        run_id: str,
        checkpoint_test_bytes: bytes,
        checkpoint_test_sha: str,
        checkpoint_manifest: dict[str, str],
        event_callback: Callable[[str, dict[str, Any]], None],
    ) -> None:
        self.provider = provider
        self.computer = computer
        self.sandbox_name = sandbox_name
        self.run_id = run_id
        self.checkpoint_test_bytes = checkpoint_test_bytes
        self.checkpoint_test_sha = checkpoint_test_sha
        self.checkpoint_manifest = checkpoint_manifest
        self.event_callback = event_callback

    def rollback(self) -> None:
        raise PolicyUnavailable("cloud", "Celesto Cloud does not support snapshot/rollback API")

    def handle_step7_failure(
        self,
        step7_executor: Callable[[GuestHandle], tuple[bool, str, str]],
        stage_replay_callback: Callable[[GuestHandle], None] | None = None,
    ) -> RecoveryResult:
        logger.warning("Step 7 failed. Initiating recovery policy: %s", FAILURE_POLICY)
        self.event_callback("policy_selected", {"policy": FAILURE_POLICY})

        resume_ready_s = 0.0

        for attempt in range(1, RESUME_MAX_ATTEMPTS + 1):
            self.event_callback("resume_started", {"attempt": attempt})
            t0 = time.monotonic()

            try:
                # Call resume method on provider
                self.provider.resume(
                    self.computer, origin="pipeline", step="recovery", run_id=self.run_id
                )
                res = self.provider.run(
                    self.computer,
                    "python3 --version",
                    origin="pipeline",
                    timeout=15,
                    step="recovery",
                    run_id=self.run_id,
                )
                if not res.ok:
                    raise RuntimeError(f"Computer unready after restart: {res.stderr}")
            except Exception as exc:
                logger.error("Failed to resume computer on attempt %d: %s", attempt, exc)
                continue

            resume_ready_s = time.monotonic() - t0

            # Integrity verification
            integrity_ok = False
            try:
                current_data = self.provider.read_file(
                    self.computer,
                    TEST_FILE_PATH,
                    origin="pipeline",
                    step="recovery",
                    run_id=self.run_id,
                )
                current_sha = hashlib.sha256(current_data).hexdigest()
                integrity_ok = current_sha == self.checkpoint_test_sha
            except Exception as e:
                logger.warning("Integrity check failed: %s", e)

            self.event_callback(
                "resume_verified",
                {
                    "attempt": attempt,
                    "integrity_ok": integrity_ok,
                    "resume_ready_s": resume_ready_s,
                },
            )

            if not integrity_ok:
                logger.warning("Integrity check failed; escalating to fresh start")
                break

            self.event_callback("policy_applied", {"policy": "resume", "attempt": attempt})

            # Clear cache and retry step 7 execution
            try:
                self.provider.run(
                    self.computer,
                    "rm -rf /workspace/case/.pytest_cache",
                    origin="pipeline",
                    step="recovery",
                    run_id=self.run_id,
                )
            except Exception as exc:
                logger.debug("Cache clear warning during recovery: %s", exc)

            self.event_callback("step_started", {"step": 7, "name": "execute_test", "retry": True})
            success, stdout, stderr = step7_executor(self.computer)
            if success:
                logger.info("Step 7 retry succeeded under resume policy on attempt %d", attempt)
                return RecoveryResult(
                    recovered=True,
                    policy_applied="resume",
                    attempts=attempt,
                    resume_ready_s=resume_ready_s,
                )

        # Fresh start fallback
        self.event_callback("policy_escalated", {"from_policy": "resume", "to_policy": "fresh"})
        logger.warning("Resume attempts exhausted; executing fresh start fallback")

        new_label = new_sandbox_name()
        try:
            fresh_handle = self.provider.create(new_label)
            if stage_replay_callback:
                stage_replay_callback(fresh_handle)

            # Write test from checkpoint
            self.provider.write_file(
                fresh_handle,
                TEST_FILE_PATH,
                self.checkpoint_test_bytes,
                origin="pipeline",
                step="recovery_fresh",
                run_id=self.run_id,
            )

            self.event_callback("policy_applied", {"policy": "fresh", "attempts": 1})
            success, stdout, stderr = step7_executor(fresh_handle)
            if success:
                logger.info("Fresh fallback succeeded on new sandbox %s", new_label)
                return RecoveryResult(
                    recovered=True,
                    policy_applied="fresh",
                    attempts=1,
                    resume_ready_s=resume_ready_s,
                    fallback_computer=fresh_handle,
                    fallback_sandbox_name=new_label,
                )
        except Exception as exc:
            logger.error("Fresh fallback failed: %s", exc)
            return RecoveryResult(
                recovered=False,
                policy_applied="fresh_failed",
                attempts=1,
                resume_ready_s=resume_ready_s,
                error=str(exc),
            )

        return RecoveryResult(
            recovered=False,
            policy_applied="fresh_failed",
            attempts=1,
            resume_ready_s=resume_ready_s,
            error="Fresh fallback did not reproduce failure",
        )
