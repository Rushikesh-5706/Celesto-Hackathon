from __future__ import annotations

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from typing import Any

from reprobox.pipeline.orchestrator import run_pipeline
from reprobox.sandbox.audited_provider import AuditedProvider
from reprobox.sandbox.celesto_provider import list_cloud_instances
from reprobox.sandbox.factory import get_default_provider
from reprobox.sandbox.lifecycle import sweep_orphans
from reprobox.sandbox.naming import new_sandbox_name
from reprobox.settings import settings

logger = logging.getLogger(__name__)


def run_concurrency_harness(
    num_jobs: int = 6,
    provider: AuditedProvider | None = None,
) -> dict[str, Any]:
    prov = provider or get_default_provider()
    evidence_file = settings.reports_dir / "evidence" / "concurrency_runs.jsonl"
    evidence_file.parent.mkdir(parents=True, exist_ok=True)

    cases = [f"case-{i:03d}" for i in range(1, num_jobs + 1)]
    job_results: list[dict[str, Any]] = []

    logger.info("Starting concurrency test with %d parallel jobs", num_jobs)
    t_start = time.monotonic()

    # Background sampler thread
    max_active_observed = 0
    stop_sampler = threading.Event()

    def sampler() -> None:
        nonlocal max_active_observed
        while not stop_sampler.is_set():
            try:
                active, _ = list_cloud_instances(limit=50)
                if len(active) > max_active_observed:
                    max_active_observed = len(active)
            except Exception as exc:
                logger.debug("Sampler poll warning: %s", exc)
            time.sleep(1.5)

    sampler_thread = threading.Thread(target=sampler, daemon=True)
    sampler_thread.start()

    def run_single_job(case_id: str) -> dict[str, Any]:
        sandbox_name = new_sandbox_name()
        run_id = f"run-conc-{sandbox_name[4:]}"
        started_at = datetime.now(UTC).isoformat()

        job_entry = {
            "sandbox_name": sandbox_name,
            "computer_id": "unknown",
            "started_at": started_at,
            "case_id": case_id,
            "run_id": run_id,
            "success": False,
            "wall_clock_s": 0.0,
            "cost_usd": 0.0,
            "llm_rate_limit_count": 0,
            "error": "",
        }

        try:
            res = run_pipeline(
                run_id=run_id,
                sandbox_name=sandbox_name,
                case_id=case_id,
                provider=prov,
            )
            job_entry["computer_id"] = res.computer_id
            job_entry["success"] = res.success
            job_entry["wall_clock_s"] = res.wall_clock_s
            job_entry["cost_usd"] = res.cost_usd
            job_entry["llm_rate_limit_count"] = res.rate_limit_count
            if not res.success:
                job_entry["error"] = res.failure_reason or "failed"
        except Exception as exc:
            job_entry["success"] = False
            job_entry["error"] = str(exc)

        return job_entry

    with ThreadPoolExecutor(max_workers=num_jobs) as executor:
        futures = [executor.submit(run_single_job, c) for c in cases]
        for fut in as_completed(futures):
            res = fut.result()
            job_results.append(res)
            with evidence_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(res) + "\n")

    stop_sampler.set()
    sampler_thread.join(timeout=3.0)

    total_wall_clock_s = round(time.monotonic() - t_start, 3)

    # Clean up
    sweep_orphans(prov)

    # Return summary dict
    return {
        "job_count": len(job_results),
        "total_wall_clock_s": total_wall_clock_s,
        "max_active_observed": max_active_observed,
        "job_results": job_results,
    }
