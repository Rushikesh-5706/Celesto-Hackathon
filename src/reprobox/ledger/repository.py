"""Repository layer for persisting runs and events in PostgreSQL."""

from __future__ import annotations

import json
from typing import Any

from reprobox.ledger.database import get_connection
from reprobox.ledger.models import EventRecord, RunRecord


class LedgerRepository:
    """Postgres-backed repository for runs and lifecycle events."""

    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url

    def upsert_run(self, run: RunRecord) -> RunRecord:
        """Insert or update a run record keyed on run_id."""
        query = """
        INSERT INTO runs (run_id, sandbox_name, problem_id, state, execution_target, outcome, updated_at)
        VALUES (%(run_id)s, %(sandbox_name)s, %(problem_id)s, %(state)s, %(execution_target)s, %(outcome)s, now())
        ON CONFLICT (run_id) DO UPDATE SET
            sandbox_name = EXCLUDED.sandbox_name,
            problem_id = EXCLUDED.problem_id,
            state = EXCLUDED.state,
            execution_target = EXCLUDED.execution_target,
            outcome = COALESCE(EXCLUDED.outcome, runs.outcome),
            updated_at = now()
        RETURNING run_id, sandbox_name, problem_id, state, execution_target, outcome, created_at, updated_at;
        """
        params = {
            "run_id": run.run_id,
            "sandbox_name": run.sandbox_name,
            "problem_id": run.problem_id,
            "state": run.state,
            "execution_target": run.execution_target,
            "outcome": run.outcome,
        }
        with get_connection(self.database_url) as conn, conn.cursor() as cur:
            cur.execute(query, params)
            row = cur.fetchone()
            assert row is not None
            return RunRecord(
                run_id=row["run_id"],
                sandbox_name=row["sandbox_name"],
                problem_id=row["problem_id"],
                state=row["state"],
                execution_target=row["execution_target"],
                outcome=row["outcome"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def get_run(self, run_id: str) -> RunRecord | None:
        """Fetch a single run by run_id."""
        query = """
        SELECT run_id, sandbox_name, problem_id, state, execution_target, outcome, created_at, updated_at
        FROM runs
        WHERE run_id = %(run_id)s;
        """
        with get_connection(self.database_url) as conn, conn.cursor() as cur:
            cur.execute(query, {"run_id": run_id})
            row = cur.fetchone()
            if not row:
                return None
            return RunRecord(
                run_id=row["run_id"],
                sandbox_name=row["sandbox_name"],
                problem_id=row["problem_id"],
                state=row["state"],
                execution_target=row["execution_target"],
                outcome=row["outcome"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def list_runs(self, limit: int = 500) -> list[RunRecord]:
        """List runs ordered newest first."""
        clamped_limit = min(max(1, limit), 1000)
        query = """
        SELECT run_id, sandbox_name, problem_id, state, execution_target, outcome, created_at, updated_at
        FROM runs
        ORDER BY created_at DESC
        LIMIT %(limit)s;
        """
        with get_connection(self.database_url) as conn, conn.cursor() as cur:
            cur.execute(query, {"limit": clamped_limit})
            rows = cur.fetchall()
            return [
                RunRecord(
                    run_id=r["run_id"],
                    sandbox_name=r["sandbox_name"],
                    problem_id=r["problem_id"],
                    state=r["state"],
                    execution_target=r["execution_target"],
                    outcome=r["outcome"],
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                )
                for r in rows
            ]

    def update_state(self, run_id: str, state: str, outcome: str | None = None) -> None:
        """Update the state and optional outcome of a run."""
        query = """
        UPDATE runs
        SET state = %(state)s,
            outcome = COALESCE(%(outcome)s, outcome),
            updated_at = now()
        WHERE run_id = %(run_id)s;
        """
        with get_connection(self.database_url) as conn, conn.cursor() as cur:
            cur.execute(query, {"run_id": run_id, "state": state, "outcome": outcome})

    def append_event(
        self, run_id: str, event: str, payload: dict[str, Any] | None = None
    ) -> EventRecord:
        """Append an event to run_events."""
        query = """
        INSERT INTO run_events (run_id, event, payload, ts)
        VALUES (%(run_id)s, %(event)s, %(payload)s, now())
        RETURNING id, run_id, event, payload, ts;
        """
        params = {
            "run_id": run_id,
            "event": event,
            "payload": json.dumps(payload or {}),
        }
        with get_connection(self.database_url) as conn, conn.cursor() as cur:
            cur.execute(query, params)
            row = cur.fetchone()
            assert row is not None
            return EventRecord(
                id=row["id"],
                run_id=row["run_id"],
                event=row["event"],
                payload=row["payload"],
                ts=row["ts"],
            )

    def list_events(self, run_id: str) -> list[EventRecord]:
        """List events for a specific run ordered chronologically."""
        query = """
        SELECT id, run_id, event, payload, ts
        FROM run_events
        WHERE run_id = %(run_id)s
        ORDER BY id ASC;
        """
        with get_connection(self.database_url) as conn, conn.cursor() as cur:
            cur.execute(query, {"run_id": run_id})
            rows = cur.fetchall()
            return [
                EventRecord(
                    id=r["id"],
                    run_id=r["run_id"],
                    event=r["event"],
                    payload=r["payload"],
                    ts=r["ts"],
                )
                for r in rows
            ]
