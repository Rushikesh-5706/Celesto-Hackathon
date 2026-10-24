"""Asynchronous job execution routes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from reprobox.constants import EXECUTION_TARGET
from reprobox.ledger.models import RunRecord
from reprobox.ledger.repository import LedgerRepository
from reprobox.sandbox.naming import new_sandbox_name
from reprobox.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs")
repo = LedgerRepository()


class CreateJobRequest(BaseModel):
    case_id: str = Field(..., min_length=1)
    fault_step: int | None = None


def _check_provider_availability() -> str | None:
    """Check if Celesto provider can be used."""
    if not settings.celesto_api_key:
        return "CELESTO_API_KEY environment variable is not configured"
    import importlib.util

    if importlib.util.find_spec("celesto") is None:
        return "Celesto Python SDK is not installed or importable"
    return None


def _run_pipeline_background(
    run_id: str, sandbox_name: str, case_id: str, fault_step: int | None
) -> None:
    """Execute pipeline in a detached background thread without swallowing errors."""
    try:
        from reprobox.pipeline.orchestrator import run_pipeline

        run_pipeline(
            run_id=run_id, sandbox_name=sandbox_name, case_id=case_id, fault_step=fault_step
        )
    except Exception as exc:
        logger.exception("Background pipeline execution failed for run_id %s: %s", run_id, exc)
        repo.append_event(
            run_id,
            "pipeline_exception",
            {"error": str(exc), "error_type": type(exc).__name__},
        )
        repo.update_state(run_id, "failed", outcome="failed")


@router.post("", status_code=202)
def start_job(req: CreateJobRequest, background_tasks: BackgroundTasks) -> JSONResponse:
    """Start an asynchronous bug reproduction pipeline job."""
    unavailable_reason = _check_provider_availability()
    if unavailable_reason:
        return JSONResponse(
            status_code=503,
            content={"error": "celesto_unavailable", "detail": unavailable_reason},
        )

    # Validate case existence
    case_dir = settings.fixtures_dir / req.case_id
    if not (case_dir / "case.json").exists():
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_request", "detail": f"Case '{req.case_id}' does not exist"},
        )

    run_id = f"run-{new_sandbox_name()[4:]}"
    sandbox_name = new_sandbox_name()

    # Initial ledger record
    repo.upsert_run(
        RunRecord(
            run_id=run_id,
            sandbox_name=sandbox_name,
            problem_id=req.case_id,
            state="created",
            execution_target=EXECUTION_TARGET,
        )
    )

    background_tasks.add_task(
        _run_pipeline_background,
        run_id=run_id,
        sandbox_name=sandbox_name,
        case_id=req.case_id,
        fault_step=req.fault_step,
    )

    return JSONResponse(
        status_code=202,
        content={"run_id": run_id, "sandbox_name": sandbox_name, "state": "created"},
    )


@router.get("/{run_id}")
def get_job(run_id: str) -> JSONResponse:
    """Check the status and outcome of a job."""
    run = repo.get_run(run_id)
    if not run:
        return JSONResponse(
            status_code=404, content={"error": "not_found", "detail": f"Job '{run_id}' not found"}
        )

    return JSONResponse(
        status_code=200,
        content={
            "run_id": run.run_id,
            "sandbox_name": run.sandbox_name,
            "problem_id": run.problem_id,
            "state": run.state,
            "outcome": run.outcome,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "updated_at": run.updated_at.isoformat() if run.updated_at else None,
        },
    )
