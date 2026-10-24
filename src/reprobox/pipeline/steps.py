from __future__ import annotations

import hashlib
import logging
import time

from reprobox.agent.loop import AgentLoop
from reprobox.constants import TEST_FILE_PATH
from reprobox.pipeline.cases import CaseFixture
from reprobox.sandbox.audited_provider import AuditedProvider
from reprobox.sandbox.handle import GuestHandle

logger = logging.getLogger(__name__)


def step_boot_probe(
    provider: AuditedProvider,
    guest: GuestHandle,
    sandbox_name: str,
    run_id: str,
    timeout_s: int = 120,
) -> float:
    t0 = time.monotonic()
    delay = 1.0

    while time.monotonic() - t0 < timeout_s:
        try:
            res = provider.run(
                guest,
                "python3 --version",
                origin="pipeline",
                step="boot_probe",
                run_id=run_id,
                timeout=10,
            )
            if res.ok:
                pytest_check = provider.run(
                    guest,
                    "python3 -m pytest --version",
                    origin="pipeline",
                    step="boot_probe",
                    run_id=run_id,
                    timeout=10,
                )
                if not pytest_check.ok:
                    logger.info("Installing pytest into guest sandbox")
                    provider.run(
                        guest,
                        "python3 -m pip install pytest",
                        origin="pipeline",
                        step="boot_probe",
                        run_id=run_id,
                        timeout=60,
                    )
                return time.monotonic() - t0
        except Exception as e:
            logger.debug("Boot probe retrying: %s", e)

        time.sleep(delay)
        delay = min(delay * 1.5, 5.0)

    raise TimeoutError(f"Sandbox {sandbox_name} did not become ready within {timeout_s}s")


def step_stage_case(
    provider: AuditedProvider,
    guest: GuestHandle,
    sandbox_name: str,
    run_id: str,
    case: CaseFixture,
) -> dict[str, str]:
    provider.run(
        guest, "mkdir -p /workspace/case", origin="pipeline", step="stage_case", run_id=run_id
    )

    manifest: dict[str, str] = {}
    file_map: dict[str, bytes] = {}

    # Upload all files in repo/, skipping dotfiles for security
    for file_path in sorted(case.repo_path.glob("**/*")):
        if file_path.is_file() and not file_path.name.startswith("."):
            rel = file_path.relative_to(case.repo_path)
            guest_dest = f"/workspace/case/{rel}"
            data = file_path.read_bytes()
            file_map[guest_dest] = data
            manifest[str(rel)] = hashlib.sha256(data).hexdigest()

    file_map["/workspace/case/issue.md"] = case.issue_text.encode("utf-8")
    provider.write_files(guest, file_map, origin="pipeline", step="stage_case", run_id=run_id)

    provider.run(
        guest, "mkdir -p /workspace/case/tests", origin="pipeline", step="stage_case", run_id=run_id
    )
    return manifest


def step_baseline(
    provider: AuditedProvider,
    guest: GuestHandle,
    sandbox_name: str,
    run_id: str,
) -> bool:
    res = provider.run(
        guest,
        "python3 -m pytest /workspace/case -p no:cacheprovider",
        origin="pipeline",
        step="baseline",
        run_id=run_id,
        timeout=45,
    )
    return res.ok


def step_agent_loop(
    provider: AuditedProvider,
    guest: GuestHandle,
    sandbox_name: str,
    run_id: str,
    case: CaseFixture,
    initial_manifest: dict[str, str],
) -> tuple[bool, int, int, str]:
    agent = AgentLoop(provider=provider, guest=guest, run_id=run_id, sandbox_name=sandbox_name)
    res = agent.run(case.title, case.issue_text)

    if not res.test_authored:
        reason = res.failure_reason or "agent_no_test"
        return False, res.prompt_tokens, res.completion_tokens, reason

    # Verify source integrity: no non-test source files modified
    for rel_path, expected_sha in initial_manifest.items():
        if rel_path.startswith("tests/test_issue_repro.py"):
            continue
        guest_file = f"/workspace/case/{rel_path}"
        try:
            current_data = provider.read_file(
                guest, guest_file, origin="pipeline", step="agent_loop", run_id=run_id
            )
            current_sha = hashlib.sha256(current_data).hexdigest()
            if current_sha != expected_sha:
                return False, res.prompt_tokens, res.completion_tokens, "source_modified"
        except Exception:
            return False, res.prompt_tokens, res.completion_tokens, "source_modified"

    return True, res.prompt_tokens, res.completion_tokens, "ok"


def step_execute_test(
    provider: AuditedProvider,
    guest: GuestHandle,
    sandbox_name: str,
    run_id: str,
    timeout: int = 30,
) -> tuple[bool, str, str]:
    cmd = f"python3 -m pytest {TEST_FILE_PATH} -p no:cacheprovider --junitxml=/workspace/case/junit.xml"
    res = provider.run(
        guest,
        cmd,
        origin="pipeline",
        step="execute_test",
        run_id=run_id,
        timeout=timeout,
    )
    # Expected exit code is 1 (failure)
    success = res.exit_code == 1
    return success, res.stdout, res.stderr


def step_verify_reference(
    provider: AuditedProvider,
    guest: GuestHandle,
    sandbox_name: str,
    run_id: str,
    case: CaseFixture,
) -> bool:
    provider.run(
        guest,
        "mkdir -p /workspace/scratch_ref",
        origin="pipeline",
        step="verify_reference",
        run_id=run_id,
    )
    provider.run(
        guest,
        "cp -r /workspace/case/. /workspace/scratch_ref/",
        origin="pipeline",
        step="verify_reference",
        run_id=run_id,
    )

    ref_map: dict[str, bytes] = {}
    for ref_file in sorted(case.reference_path.glob("**/*")):
        if ref_file.is_file() and not ref_file.name.startswith("."):
            rel = ref_file.relative_to(case.reference_path)
            dest = f"/workspace/scratch_ref/{rel}"
            ref_map[dest] = ref_file.read_bytes()
    provider.write_files(guest, ref_map, origin="pipeline", step="verify_reference", run_id=run_id)

    cmd = "python3 -m pytest /workspace/scratch_ref/tests/test_issue_repro.py -p no:cacheprovider"
    res = provider.run(
        guest, cmd, origin="pipeline", step="verify_reference", run_id=run_id, timeout=30
    )
    return res.ok
