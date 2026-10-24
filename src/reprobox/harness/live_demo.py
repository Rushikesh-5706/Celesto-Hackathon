from __future__ import annotations

import logging
import time

from reprobox.pipeline.orchestrator import run_pipeline
from reprobox.sandbox.audited_provider import AuditedProvider
from reprobox.sandbox.factory import get_default_provider
from reprobox.sandbox.naming import new_sandbox_name

logger = logging.getLogger(__name__)


def run_live_demo(case_id: str = "case-007", provider: AuditedProvider | None = None) -> None:
    print(f"Target case: {case_id}")
    prov = provider or get_default_provider()
    sandbox_name = new_sandbox_name()
    run_id = f"demo-{sandbox_name[4:]}"

    print(f"Starting run {run_id} with sandbox label {sandbox_name}...")
    t0 = time.monotonic()

    res = run_pipeline(
        run_id=run_id,
        sandbox_name=sandbox_name,
        case_id=case_id,
        provider=prov,
        publish_preview=True,
    )
    elapsed = time.monotonic() - t0

    print(f"\nDemo completed in {elapsed:.2f}s:")
    print(f"Outcome: {'SUCCESS' if res.success else 'FAILED'}")
    print(f"Sandbox label: {res.sandbox_name}")
    print(f"Computer id: {res.computer_id}")
    print(f"Wall clock: {res.wall_clock_s:.2f}s")
    print(f"Boot to ready: {res.boot_to_ready_s:.2f}s")
    print(f"Tokens: prompt={res.prompt_tokens}, completion={res.completion_tokens}")
    print(f"Estimated cost: ${res.cost_usd:.5f}")
    if res.preview_url_status:
        print(f"Preview URL fetch status: {res.preview_url_status}")
    if res.failure_reason:
        print(f"Failure reason: {res.failure_reason}")
