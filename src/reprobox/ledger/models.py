"""Domain models for the run ledger."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class RunRecord:
    run_id: str
    sandbox_name: str
    problem_id: str
    state: str
    execution_target: str
    outcome: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "sandbox_name": self.sandbox_name,
            "problem_id": self.problem_id,
            "state": self.state,
            "execution_target": self.execution_target,
            "outcome": self.outcome,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


@dataclass
class EventRecord:
    run_id: str
    event: str
    payload: dict[str, Any] = field(default_factory=dict)
    id: int | None = None
    ts: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "event": self.event,
            "payload": self.payload,
            "ts": self.ts.isoformat() if self.ts else None,
        }
