"""Recovery mechanics for mid-task failure at Step 7 under the resume policy."""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from reprobox.constants import FAILURE_POLICY, RESUME_MAX_ATTEMPTS, TEST_FILE_PATH
from reprobox.sandbox.provider import ComputerProvider

logger = logging.getLogger(__name__)


@dataclass
class RecoveryResult:
    recovered: bool
    policy_applied: str
    attempts: int
    resume_ready_s: float
    fallback_computer: Any | None = None
    fallback_sandbox_name: str | None = None
    error: str | None = None


class RecoveryHandler:
    """Implements Step 7 recovery policy: resume in-place, fall back to fresh start."""

    def __init__(
        self,
        provider: ComputerProvider,
        computer: Any,
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

    def handle_step7_failure(
        self,
        step7_executor: Callable[[Any], tuple[bool, str, str]],
    ) -> RecoveryResult:
        """Execute recovery procedure following step 7 failure."""
        logger.warning("Step 7 failed. Initiating recovery policy: %s", FAILURE_POLICY)
        self.event_callback("policy_selected", {"policy": FAILURE_POLICY})

        # Up to RESUME_MAX_ATTEMPTS attempts to resume in-place
        for attempt in range(1, RESUME_MAX_ATTEMPTS + 1):
            self.event_callback("resume_started", {"attempt": attempt})
            t0 = time.monotonic()

            try:
                # Ensure computer is running
                self.provider.start(self.computer)
                # Verify boot responsiveness
                res = self.provider.run(self.computer, "python3 --version", timeout=15)
                if res.exit_code != 0:
                    raise RuntimeError(f"Computer unready after restart: {res.stderr}")
            except Exception as exc:
                logger.error("Failed to start/verify computer on resume attempt %d: %s", attempt, exc)
                continue

            resume_ready_s = time.monotonic() - t0

            # Integrity verification: test file sha256 must match checkpoint
            integrity_ok = False
            try:
                current_data = self.provider.read_file(self.computer, TEST_FILE_PATH)
                current_sha = hashlib.sha256(current_data).hexdigest()
                integrity_ok = (current_sha == self.checkpoint_test_sha)
            except Exception as e:
                logger.warning("Integrity check failed to read test file: %s", e)

            self.event_callback(
                "resume_verified",
                {"attempt": attempt, "integrity_ok": integrity_ok, "resume_ready_s": resume_ready_s},
            )

            if not integrity_ok:
                logger.warning("Integrity check failed. Escalating from resume to fresh...")
                break

            self.event_callback("policy_applied", {"policy": "resume", "attempt": attempt})

            # Clear cache and retry step 7 execution
            self.provider.run(self.computer, "rm -rf /workspace/case/.pytest_cache")
            success, stdout, stderr = step7_executor(self.computer)
            if success:
                logger.info("Step 7 retry succeeded under resume policy on attempt %d", attempt)
                return RecoveryResult(
                    recovered=True,
                    policy_applied="resume",
                    attempts=attempt,
                    resume_ready_s=resume_ready_s,
                )

        # If resume failed or integrity violated, escalate to fresh start
        self.event_callback("policy_escalated", {"from_policy": "resume", "to_policy": "fresh"})
        logger.warning("Resume policy exhausted. Executing fresh start fallback...")

        return RecoveryResult(
            recovered=False,
            policy_applied="fresh_required",
            attempts=RESUME_MAX_ATTEMPTS,
            resume_ready_s=0.0,
            error="Resume attempts exhausted; fresh start required",
        )
