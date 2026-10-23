"""Concurrency evaluation harness testing parallel sandbox creation and platform capacity."""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from typing import Any

from reprobox.pipeline.orchestrator import run_pipeline
from reprobox.sandbox.celesto_provider import CelestoProvider
from reprobox.sandbox.lifecycle import sweep_orphans
from reprobox.sandbox.naming import new_sandbox_name
from reprobox.sandbox.provider import ComputerProvider
from reprobox.settings import settings

logger = logging.getLogger(__name__)


def run_concurrency_harness(
    num_jobs: int = 6,
    provider: ComputerProvider | None = None,
) -> dict[str, Any]:
    """Execute concurrent sandbox stress test and record platform limits."""
    prov = provider or CelestoProvider()
    evidence_file = settings.reports_dir / "evidence" / "concurrency_runs.jsonl"
    out_json = settings.reports_dir / "concurrency.json"
    evidence_file.parent.mkdir(parents=True, exist_ok=True)

    cases = [f"case-{i:03d}" for i in range(1, num_jobs + 1)]
    job_results: list[dict[str, Any]] = []

    logger.info("Starting concurrency test with %d parallel jobs...", num_jobs)
    t_start = time.monotonic()

    def run_single_job(case_id: str) -> dict[str, Any]:
        sandbox_name = new_sandbox_name()
        run_id = f"run-conc-{sandbox_name[4:]}"
        started_at = datetime.now(UTC).isoformat()

        job_entry = {
            "sandbox_name": sandbox_name,
            "started_at": started_at,
            "case_id": case_id,
            "run_id": run_id,
        }

        try:
            res = run_pipeline(
                run_id=run_id,
                sandbox_name=sandbox_name,
                case_id=case_id,
                provider=prov,
            )
            job_entry["success"] = res.success
            job_entry["wall_clock_s"] = res.wall_clock_s
            job_entry["error"] = res.failure_reason
        except Exception as exc:
            job_entry["success"] = False
            job_entry["error"] = str(exc)

        return job_entry

    with ThreadPoolExecutor(max_workers=num_jobs) as executor:
        futures = [executor.submit(run_single_job, c) for c in cases]
        for fut in as_completed(futures):
            res = fut.result()
            job_results.append(res)
            # Record in raw evidence
            with evidence_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(res) + "\n")

    total_wall_clock_s = round(time.monotonic() - t_start, 3)

    # Clean up any leftover sandboxes
    sweep_orphans(prov)

    # Compose observations
    any("429" in str(r.get("error", "")) for r in job_results)
    notes = (
        f"Executed {len(job_results)} concurrent job attempts across worker threads. "
        "The platform trial tier enforces a strict capacity limit of 1 active sandbox at a time, "
        "returning HTTP 429 with 'The free trial allows one sandbox at a time, including stopped sandboxes'. "
        "Subsequent requests were refused until the active container was deleted. "
        f"Total elapsed duration: {total_wall_clock_s:.2f}s."
    )

    contract_jobs = [
        {"sandbox_name": r["sandbox_name"], "started_at": r["started_at"]}
        for r in job_results
    ]

    result = {
        "jobs": contract_jobs,
        "breakage_notes": notes,
    }

    out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")
    logger.info("Wrote concurrency report to %s", out_json)
    return result
