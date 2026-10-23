"""Step 7 mid-task failure demonstration and policy trace capture."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from reprobox.constants import (
    FAILURE_POLICY,
    FAULT_STEP,
    TOTAL_STEPS,
)
from reprobox.ledger.repository import LedgerRepository
from reprobox.pipeline.orchestrator import run_pipeline
from reprobox.sandbox.naming import new_sandbox_name
from reprobox.sandbox.provider import ComputerProvider
from reprobox.settings import settings

logger = logging.getLogger(__name__)

POLICY_RATIONALE = (
    "Steps 1 through 6 encompass sandbox provisioning, dependency probe, project staging, baseline testing, "
    "and model deliberation. These initial steps consume significant wall-clock time and token budget. In contrast, "
    "Step 7 only executes the newly authored test using pytest against a read-only codebase. The resume policy "
    "leverages the intact filesystem state and idempotency of test execution to retry in-place after verifying "
    "source tree integrity and test file SHA-256 digests. This avoids discarding a healthy container, saves re-boot "
    "latency, and prevents repeating non-deterministic model generation."
)


def run_failure_demo(
    provider: ComputerProvider | None = None,
    case_id: str = "dev-001",
) -> None:
    """Execute dev case with Step 7 fault injection and generate contract evidence."""
    run_id = f"run-failure-{new_sandbox_name()[4:]}"
    sandbox_name = new_sandbox_name()
    repo = LedgerRepository()

    trace_file = settings.reports_dir / "failure_trace.jsonl"
    policy_file = settings.reports_dir / "failure_policy.json"
    trace_file.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Executing Step 7 failure demonstration on case %s...", case_id)
    run_pipeline(
        run_id=run_id,
        sandbox_name=sandbox_name,
        case_id=case_id,
        fault_step=FAULT_STEP,
        provider=provider,
        repository=repo,
    )

    # Collect events recorded in the ledger for this run
    events = repo.list_events(run_id)

    with trace_file.open("w", encoding="utf-8") as f:
        for ev in events:
            record: dict[str, Any] = {
                "ts": ev.ts.isoformat() if ev.ts else datetime.now(UTC).isoformat(),
                "run_id": run_id,
                "sandbox_name": sandbox_name,
                "event": ev.event,
            }
            if ev.payload:
                if "step" in ev.payload:
                    record["step"] = ev.payload["step"]
                if "policy" in ev.payload:
                    record["policy"] = ev.payload["policy"]
                if "method" in ev.payload:
                    record["method"] = ev.payload["method"]
                if "attempt" in ev.payload:
                    record["attempt"] = ev.payload["attempt"]

            f.write(json.dumps(record) + "\n")

    logger.info("Wrote failure trace to %s", trace_file)

    # Write failure_policy.json per exact contract
    policy_data = {
        "failed_step": FAULT_STEP,
        "total_steps": TOTAL_STEPS,
        "policy": FAILURE_POLICY,
        "rationale": POLICY_RATIONALE,
        "trace_path": "reports/failure_trace.jsonl",
    }
    policy_file.write_text(json.dumps(policy_data, indent=2), encoding="utf-8")
    logger.info("Wrote failure policy metadata to %s", policy_file)
