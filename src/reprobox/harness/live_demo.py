"""Interactive live demo runner formatted for video walkthrough capture."""

from __future__ import annotations

import logging
import time

from reprobox.pipeline.orchestrator import run_pipeline
from reprobox.sandbox.celesto_provider import CelestoProvider
from reprobox.sandbox.naming import new_sandbox_name
from reprobox.sandbox.provider import ComputerProvider

logger = logging.getLogger(__name__)


def run_live_demo(case_id: str = "case-007", provider: ComputerProvider | None = None) -> None:
    """Run interactive visual pipeline demonstration."""
    print("=" * 60)
    print("  REPROBOX LIVE BUG REPRODUCTION DEMO")
    print(f"  Target Case: {case_id}")
    print("=" * 60)

    prov = provider or CelestoProvider()
    sandbox_name = new_sandbox_name()
    run_id = f"demo-{sandbox_name[4:]}"

    print(f"[*] Initializing sandbox: {sandbox_name}")
    print(f"[*] Run ID: {run_id}")
    print("[*] Launching 10-step reproduction pipeline...\n")

    t0 = time.monotonic()
    res = run_pipeline(
        run_id=run_id,
        sandbox_name=sandbox_name,
        case_id=case_id,
        provider=prov,
    )
    time.monotonic() - t0

    print("\n" + "=" * 60)
    print("  DEMO EXECUTION RESULTS")
    print("=" * 60)
    print(f"  Outcome:          {'SUCCESS' if res.success else 'FAILED'}")
    print(f"  Wall Clock Time:  {res.wall_clock_s:.2f}s")
    print(f"  Boot to Ready:    {res.boot_to_ready_s:.2f}s")
    print(f"  Prompt Tokens:    {res.prompt_tokens}")
    print(f"  Complete Tokens:  {res.completion_tokens}")
    print(f"  Computed Cost:    ${res.cost_usd:.6f}")
    if res.failure_reason:
        print(f"  Failure Reason:   {res.failure_reason}")
    print("=" * 60)
