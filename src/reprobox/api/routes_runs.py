"""Run management and inspection endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from reprobox.constants import EXECUTION_TARGET, LIFECYCLE_STATES, SANDBOX_NAME_RE
from reprobox.ledger.models import RunRecord
from reprobox.ledger.repository import LedgerRepository

router = APIRouter(prefix="/api/runs")
repo = LedgerRepository()


class CreateRunRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    run_id: str = Field(..., min_length=1)
    sandbox_name: str = Field(..., min_length=1)
    problem_id: str = Field(..., min_length=1)
    state: str = Field(..., min_length=1)
    execution_target: str = Field(..., min_length=1)

    @field_validator("execution_target")
    @classmethod
    def validate_execution_target(cls, v: str) -> str:
        if v != EXECUTION_TARGET:
            raise ValueError(f"execution_target must be '{EXECUTION_TARGET}', got '{v}'")
        return v

    @field_validator("state")
    @classmethod
    def validate_state(cls, v: str) -> str:
        if v not in LIFECYCLE_STATES:
            raise ValueError(f"state must be one of {LIFECYCLE_STATES}, got '{v}'")
        return v

    @field_validator("sandbox_name")
    @classmethod
    def validate_sandbox_name(cls, v: str) -> str:
        if not SANDBOX_NAME_RE.match(v):
            raise ValueError(f"sandbox_name must match '^sbx-[a-z0-9]{{8,}}$', got '{v}'")
        return v


@router.get("")
def list_runs(limit: int = Query(500, ge=1, le=1000)) -> list[dict[str, Any]]:
    """List runs ordered newest first."""
    runs = repo.list_runs(limit=limit)
    return [r.to_dict() for r in runs]


@router.post("", status_code=201)
def create_run(req: CreateRunRequest) -> JSONResponse:
    """Create or upsert a run record."""
    record = RunRecord(
        run_id=req.run_id,
        sandbox_name=req.sandbox_name,
        problem_id=req.problem_id,
        state=req.state,
        execution_target=req.execution_target,
    )
    saved = repo.upsert_run(record)
    return JSONResponse(status_code=201, content=saved.to_dict())


@router.get("/{run_id}")
def get_run(run_id: str) -> JSONResponse:
    """Fetch run by ID."""
    run = repo.get_run(run_id)
    if not run:
        return JSONResponse(status_code=404, content={"error": "not_found", "detail": f"Run '{run_id}' not found"})
    return JSONResponse(status_code=200, content=run.to_dict())


@router.get("/{run_id}/events")
def get_run_events(run_id: str) -> JSONResponse:
    """List lifecycle events for a run."""
    run = repo.get_run(run_id)
    if not run:
        return JSONResponse(status_code=404, content={"error": "not_found", "detail": f"Run '{run_id}' not found"})
    events = repo.list_events(run_id)
    return JSONResponse(status_code=200, content=[e.to_dict() for e in events])
