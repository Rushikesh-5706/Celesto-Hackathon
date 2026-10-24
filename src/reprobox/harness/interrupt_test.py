"""Lifecycle interrupt test delivering SIGINT during pipeline execution."""

from __future__ import annotations

import logging
import signal
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from reprobox.ledger.repository import LedgerRepository
from reprobox.pipeline.orchestrator import run_pipeline
from reprobox.sandbox.celesto_provider import list_cloud_instances
from reprobox.sandbox.factory import get_default_provider
from reprobox.sandbox.lifecycle import install_cleanup_handlers
from reprobox.sandbox.naming import new_sandbox_name
from reprobox.settings import settings

logger = logging.getLogger(__name__)


def run_interrupt_test(
    case_id: str = "dev-002",
    log_path: Path | None = None,
) -> bool:
    """Run dev-002, deliver SIGINT while running, verify sandbox deletion in SDK and ledger."""
    install_cleanup_handlers()

    target_log = log_path or (settings.evidence_dir / "lifecycle_interrupt.log")
    target_log.parent.mkdir(parents=True, exist_ok=True)

    run_id = f"run-intr-{new_sandbox_name()[4:]}"
    sandbox_name = new_sandbox_name()
    repo = LedgerRepository(settings.harness_database_url)

    provider = get_default_provider()

    lines: list[str] = [
        f"=== LIFECYCLE INTERRUPT TEST START {datetime.now(UTC).isoformat()} ===",
        f"Case: {case_id}, run_id: {run_id}, sandbox_name: {sandbox_name}",
    ]

    stop_timer = threading.Event()

    def _deliver_sigint() -> None:
        start = time.monotonic()
        while not stop_timer.is_set() and time.monotonic() - start < 90:
            events = repo.list_events(run_id)
            step_events = [e for e in events if e.event in ("step_started", "step_completed")]
            has_step_5 = any(
                e.payload.get("step") == 5 or e.payload.get("step") == "5" for e in step_events
            )
            if has_step_5 or time.monotonic() - start > 25:
                logger.info("Delivering SIGINT to process...")
                time.sleep(1.0)
                signal.raise_signal(signal.SIGINT)
                return
            time.sleep(0.5)

    timer_thread = threading.Thread(target=_deliver_sigint, daemon=True)
    timer_thread.start()

    sigint_caught = False
    try:
        run_pipeline(
            run_id=run_id,
            sandbox_name=sandbox_name,
            case_id=case_id,
            provider=provider,
            repository=repo,
        )
    except KeyboardInterrupt:
        sigint_caught = True
        lines.append("Caught KeyboardInterrupt in main thread as expected")
    finally:
        stop_timer.set()

    cloud_comps, _ = list_cloud_instances(limit=100)
    run_rec = repo.get_run(run_id)
    computer_id = run_rec.computer_id if run_rec else None

    cid_active = any(c.get("id") == computer_id for c in cloud_comps) if computer_id else False
    ledger_state = run_rec.state if run_rec else "unknown"

    lines.append(f"Computer ID: {computer_id}")
    lines.append(f"Ledger state after interrupt: {ledger_state}")
    lines.append(f"Present in active SDK cloud listing: {cid_active}")

    success = sigint_caught and not cid_active and ledger_state in ("deleted", "failed")
    lines.append(f"Lifecycle interrupt cleanup verified: {success}")
    lines.append(f"=== LIFECYCLE INTERRUPT TEST END {datetime.now(UTC).isoformat()} ===")

    output = "\n".join(lines) + "\n"
    target_log.write_text(output, encoding="utf-8")
    print(output)
    return success
