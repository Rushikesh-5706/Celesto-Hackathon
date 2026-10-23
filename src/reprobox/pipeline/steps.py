"""Implementation of the 10 sequential pipeline steps."""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

from reprobox.agent.loop import AgentLoop
from reprobox.constants import (
    ORIGIN_PIPELINE,
    TEST_FILE_PATH,
)
from reprobox.pipeline.cases import CaseFixture
from reprobox.sandbox.audit import audit_logger
from reprobox.sandbox.guard import Guard
from reprobox.sandbox.provider import ComputerProvider, RunResult

logger = logging.getLogger(__name__)


def _guarded_pipeline_run(
    provider: ComputerProvider,
    computer: Any,
    sandbox_name: str,
    run_id: str,
    command: str,
    step: str,
    timeout: int = 60,
) -> RunResult:
    """Run a trusted pipeline command evaluated through the security guard."""
    decision = Guard.evaluate(command, origin=ORIGIN_PIPELINE)
    audit_logger.log_command(
        sandbox_name=sandbox_name,
        command=command,
        decision=decision.decision,
        run_id=run_id,
        origin=ORIGIN_PIPELINE,
        step=step,
        rule_id=decision.rule_id,
        reason=decision.reason,
    )
    if not decision.allowed:
        raise RuntimeError(f"Pipeline command blocked by guard: {decision.reason}")
    return provider.run(computer, command, timeout=timeout)


def step_boot_probe(
    provider: ComputerProvider,
    computer: Any,
    sandbox_name: str,
    run_id: str,
    timeout_s: int = 120,
) -> float:
    """Probe computer readiness until python and pytest respond."""
    t0 = time.monotonic()
    delay = 1.0

    while time.monotonic() - t0 < timeout_s:
        try:
            res = _guarded_pipeline_run(
                provider, computer, sandbox_name, run_id, "python3 --version", "boot_probe", timeout=10
            )
            if res.exit_code == 0:
                # Ensure pytest is available
                pytest_check = _guarded_pipeline_run(
                    provider, computer, sandbox_name, run_id, "python3 -m pytest --version", "boot_probe", timeout=10
                )
                if pytest_check.exit_code != 0:
                    logger.info("Installing pytest into guest sandbox...")
                    _guarded_pipeline_run(
                        provider, computer, sandbox_name, run_id, "python3 -m pip install pytest", "boot_probe", timeout=60
                    )
                return time.monotonic() - t0
        except Exception as e:
            logger.debug("Boot probe retrying after error: %s", e)

        time.sleep(delay)
        delay = min(delay * 1.5, 5.0)

    raise TimeoutError(f"Sandbox {sandbox_name} did not become ready within {timeout_s}s")


def step_stage_case(
    provider: ComputerProvider,
    computer: Any,
    sandbox_name: str,
    run_id: str,
    case: CaseFixture,
) -> dict[str, str]:
    """Upload project repository files and issue report into sandbox."""
    _guarded_pipeline_run(provider, computer, sandbox_name, run_id, "mkdir -p /workspace/case", "stage_case")

    manifest: dict[str, str] = {}

    # Upload all files in repo/
    for file_path in sorted(case.repo_path.glob("**/*")):
        if file_path.is_file() and not file_path.name.startswith("."):
            rel = file_path.relative_to(case.repo_path)
            guest_dest = f"/workspace/case/{rel}"
            data = file_path.read_bytes()
            provider.write_file(computer, guest_dest, data)
            manifest[str(rel)] = hashlib.sha256(data).hexdigest()

    # Upload issue.md
    provider.write_file(computer, "/workspace/case/issue.md", case.issue_text.encode("utf-8"))

    # Ensure tests directory exists for reproduction test
    _guarded_pipeline_run(provider, computer, sandbox_name, run_id, "mkdir -p /workspace/case/tests", "stage_case")

    return manifest


def step_baseline(
    provider: ComputerProvider,
    computer: Any,
    sandbox_name: str,
    run_id: str,
) -> bool:
    """Verify that existing test suite passes on unmodified codebase."""
    res = _guarded_pipeline_run(
        provider, computer, sandbox_name, run_id, "python3 -m pytest /workspace/case -p no:cacheprovider", "baseline", timeout=45
    )
    return res.exit_code == 0


def step_agent_loop(
    provider: ComputerProvider,
    computer: Any,
    sandbox_name: str,
    run_id: str,
    case: CaseFixture,
    initial_manifest: dict[str, str],
) -> tuple[bool, int, int, str]:
    """Execute LLM agent deliberation loop and verify source integrity."""
    agent = AgentLoop(computer, provider, sandbox_name, run_id)
    res = agent.run(case.title, case.issue_text)

    if not res.test_authored:
        return False, res.prompt_tokens, res.completion_tokens, "test_not_authored"

    # Verify source integrity: no non-test source files were modified
    for rel_path, expected_sha in initial_manifest.items():
        if rel_path.startswith("tests/test_issue_repro.py"):
            continue
        guest_file = f"/workspace/case/{rel_path}"
        try:
            current_data = provider.read_file(computer, guest_file)
            current_sha = hashlib.sha256(current_data).hexdigest()
            if current_sha != expected_sha:
                return False, res.prompt_tokens, res.completion_tokens, "source_modified"
        except Exception:
            return False, res.prompt_tokens, res.completion_tokens, "source_modified"

    return True, res.prompt_tokens, res.completion_tokens, "ok"


def step_execute_test(
    provider: ComputerProvider,
    computer: Any,
    sandbox_name: str,
    run_id: str,
    timeout: int = 30,
) -> tuple[bool, str, str]:
    """Run authored reproduction test and produce JUnit XML report."""
    cmd = f"python3 -m pytest {TEST_FILE_PATH} --junitxml=/workspace/case/junit.xml -p no:cacheprovider"
    res = _guarded_pipeline_run(provider, computer, sandbox_name, run_id, cmd, "execute_test", timeout=timeout)
    # Expected exit code is 1 (failure)
    success = (res.exit_code == 1)
    return success, res.stdout, res.stderr


def step_verify_reference(
    provider: ComputerProvider,
    computer: Any,
    sandbox_name: str,
    run_id: str,
    case: CaseFixture,
) -> bool:
    """Overlay reference fixes onto scratch directory and verify test passes."""
    _guarded_pipeline_run(provider, computer, sandbox_name, run_id, "mkdir -p /workspace/scratch_ref", "verify_reference")
    _guarded_pipeline_run(provider, computer, sandbox_name, run_id, "cp -r /workspace/case/. /workspace/scratch_ref/", "verify_reference")

    # Overlay reference fixes
    for ref_file in sorted(case.reference_path.glob("**/*")):
        if ref_file.is_file():
            rel = ref_file.relative_to(case.reference_path)
            dest = f"/workspace/scratch_ref/{rel}"
            provider.write_file(computer, dest, ref_file.read_bytes())

    # Run the test against fixed reference code
    cmd = "python3 -m pytest /workspace/scratch_ref/tests/test_issue_repro.py -p no:cacheprovider"
    res = _guarded_pipeline_run(provider, computer, sandbox_name, run_id, cmd, "verify_reference", timeout=30)
    return res.exit_code == 0
