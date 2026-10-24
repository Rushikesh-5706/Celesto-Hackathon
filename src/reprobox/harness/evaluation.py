from __future__ import annotations

import importlib.metadata
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from reprobox.pipeline.orchestrator import run_pipeline
from reprobox.sandbox.audited_provider import AuditedProvider
from reprobox.sandbox.factory import get_default_provider
from reprobox.sandbox.lifecycle import sweep_orphans
from reprobox.sandbox.naming import new_sandbox_name
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
    except (OSError, UnicodeDecodeError) as exc:
        logger.debug("Could not resolve git commit: %s", exc)
    return "uncommitted"


def run_evaluation_batch(
    run_count: int = 20,
    batch_id: str | None = None,
    provider: AuditedProvider | None = None,
) -> None:
    prov = provider or get_default_provider()
    today_str = datetime.now(UTC).strftime("%Y%m%d")
    batch = batch_id or f"eval-{today_str}-1"

    eval_file = settings.reports_dir / "evidence" / "eval_runs.jsonl"
    detail_file = settings.reports_dir / "evidence" / "eval_runs_detail.jsonl"
    eval_file.parent.mkdir(parents=True, exist_ok=True)

    completed_cases: set[str] = set()
    if eval_file.exists():
        for line in eval_file.read_text(encoding="utf-8").splitlines():
            line_str = line.strip()
            if not line_str or line_str.startswith('{"type": "header"'):
                continue
            try:
                row = json.loads(line_str)
                if row.get("batch_id") == batch and "case_id" in row:
                    completed_cases.add(row["case_id"])
            except json.JSONDecodeError as exc:
                logger.debug("Skipping invalid JSON line: %s", exc)

    if not eval_file.exists() or eval_file.stat().st_size == 0:
        try:
            sdk_ver = importlib.metadata.version("celesto")
        except importlib.metadata.PackageNotFoundError:
            sdk_ver = "0.1.8"

        header = {
            "type": "header",
            "batch_id": batch,
            "git_commit": _get_git_commit(),
            "celesto_version": sdk_ver,
            "model_id": settings.llm_model,
            "provider": "cloud",
            "sandbox_size": settings.sandbox_size,
            "sandbox_price_per_hour_usd": settings.sandbox_price_per_hour_usd,
            "llm_min_interval_s": getattr(settings, "llm_min_interval_s", 0.0),
            "started_at": datetime.now(UTC).isoformat(),
        }
        with eval_file.open("w", encoding="utf-8") as f:
            f.write(json.dumps(header) + "\n")

    cases_to_run = [f"case-{i:03d}" for i in range(1, run_count + 1)]

    for idx, case_id in enumerate(cases_to_run, 1):
        if case_id in completed_cases:
            print(
                f"[{idx}/{len(cases_to_run)}] Skipping completed {case_id} in {batch}", flush=True
            )
            continue

        sandbox_name = new_sandbox_name()
        run_id = f"run-eval-{case_id}-{sandbox_name[4:]}"
        t_start = datetime.now(UTC).isoformat()

        print(
            f"\n[{idx}/{len(cases_to_run)}] Starting eval run for {case_id} (sandbox={sandbox_name})...",
            flush=True,
        )
        try:
            res = run_pipeline(
                run_id=run_id,
                sandbox_name=sandbox_name,
                case_id=case_id,
                provider=prov,
            )
            print(
                f"[{idx}/{len(cases_to_run)}] {case_id} finished: success={res.success} in {res.wall_clock_s:.1f}s",
                flush=True,
            )

            record = {
                "batch_id": batch,
                "case_id": case_id,
                "sandbox_name": sandbox_name,
                "computer_id": res.computer_id,
                "provider": "cloud",
                "fresh": True,
                "success": res.success,
                "failure_reason": res.failure_reason,
                "wall_clock_s": res.wall_clock_s,
                "boot_to_ready_s": res.boot_to_ready_s,
                "prompt_tokens": res.prompt_tokens,
                "completion_tokens": res.completion_tokens,
                "rate_limit_count": res.rate_limit_count,
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
            # Record failure record so run is never silently dropped
            err_record = {
                "batch_id": batch,
                "case_id": case_id,
                "sandbox_name": sandbox_name,
                "computer_id": "unknown",
                "provider": "cloud",
                "fresh": True,
                "success": False,
                "failure_reason": type(exc).__name__,
                "wall_clock_s": 0.0,
                "boot_to_ready_s": 0.0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "rate_limit_count": 0,
                "cost_usd": 0.0,
                "step_durations": {},
                "started_at": t_start,
                "ended_at": datetime.now(UTC).isoformat(),
            }
            with eval_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(err_record) + "\n")
            with detail_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(err_record) + "\n")

    sweep_orphans(prov)
