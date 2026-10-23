"""20-run graded reliability evaluation harness."""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path

from reprobox.pipeline.orchestrator import run_pipeline
from reprobox.sandbox.celesto_provider import CelestoProvider
from reprobox.sandbox.lifecycle import sweep_orphans
from reprobox.sandbox.naming import new_sandbox_name
from reprobox.sandbox.provider import ComputerProvider
from reprobox.settings import settings

logger = logging.getLogger(__name__)


def _get_git_commit() -> str:
    try:
        head_file = Path(__file__).resolve().parents[3] / ".git" / "HEAD"
        if head_file.exists():
            ref = head_file.read_text().strip()
            if ref.startswith("ref: "):
                ref_path = Path(__file__).resolve().parents[3] / ".git" / ref[5:]
                if ref_path.exists():
                    return ref_path.read_text().strip()
            return ref[:40]
    except Exception:
        pass
    return "uncommitted"


def run_evaluation_batch(
    run_count: int = 20,
    batch_id: str | None = None,
    provider: ComputerProvider | None = None,
) -> None:
    """Execute sequential reliability evaluation across graded cases."""
    prov = provider or CelestoProvider()
    batch = batch_id or f"batch-{int(time.time())}"

    eval_file = settings.reports_dir / "evidence" / "eval_runs.jsonl"
    detail_file = settings.reports_dir / "evidence" / "eval_runs_detail.jsonl"
    eval_file.parent.mkdir(parents=True, exist_ok=True)

    # Check already completed cases for restartability
    completed_cases: set[str] = set()
    if eval_file.exists():
        for line in eval_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if row.get("batch_id") == batch and "case_id" in row:
                    completed_cases.add(row["case_id"])
            except Exception:
                pass

    # Write header line if new file
    if not eval_file.exists() or eval_file.stat().st_size == 0:
        header = {
            "type": "header",
            "batch_id": batch,
            "git_commit": _get_git_commit(),
            "celesto_version": "0.1.8",
            "model_id": settings.llm_model,
            "provider": "celesto_sandbox",
            "sandbox_size": settings.sandbox_size,
            "sandbox_price_per_hour_usd": settings.sandbox_price_per_hour_usd,
            "llm_input_price_per_mtok_usd": settings.llm_input_price_per_mtok_usd,
            "llm_output_price_per_mtok_usd": settings.llm_output_price_per_mtok_usd,
            "started_at": datetime.now(UTC).isoformat(),
        }
        with eval_file.open("w", encoding="utf-8") as f:
            f.write(json.dumps(header) + "\n")

    cases_to_run = [f"case-{i:03d}" for i in range(1, run_count + 1)]

    for case_id in cases_to_run:
        if case_id in completed_cases:
            logger.info("Skipping already completed case %s in batch %s", case_id, batch)
            continue

        sandbox_name = new_sandbox_name()
        run_id = f"run-eval-{case_id}-{sandbox_name[4:]}"
        t_start = datetime.now(UTC).isoformat()

        logger.info("Starting graded eval run for %s (%s)...", case_id, sandbox_name)
        try:
            res = run_pipeline(
                run_id=run_id,
                sandbox_name=sandbox_name,
                case_id=case_id,
                provider=prov,
            )

            record = {
                "batch_id": batch,
                "case_id": case_id,
                "sandbox_name": sandbox_name,
                "computer_id": res.sandbox_name,
                "provider": "celesto_sandbox",
                "fresh": True,
                "success": res.success,
                "failure_reason": res.failure_reason,
                "wall_clock_s": res.wall_clock_s,
                "boot_to_ready_s": res.boot_to_ready_s,
                "prompt_tokens": res.prompt_tokens,
                "completion_tokens": res.completion_tokens,
                "cost_usd": res.cost_usd,
                "step_durations": res.step_timings,
                "started_at": t_start,
                "ended_at": datetime.now(UTC).isoformat(),
            }

            with eval_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")

            with detail_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")

        except Exception as exc:
            logger.error("Failed eval run on %s: %s", case_id, exc)

    # Perform orphan sweep at the end of the batch
    sweep_orphans(prov)
