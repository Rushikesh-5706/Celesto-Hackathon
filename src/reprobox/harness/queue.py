"""Queue harness: runs evidence steps in fixed order then reruns.

Order: failure-demo, containment, interrupt-test, rerun --until HH:MM
Each step is executed fully before the next. All failures are recorded with their reason.
No step is dropped; if a sandbox step fails due to a harness bug, the error is logged
and the queue continues.
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


def run_queue(until: str = "13:00") -> None:
    """Run all evidence steps in fixed order then reruns up to `until` time.

    Steps:
    1. failure-demo (dev-001)
    2. containment
    3. interrupt-test
    4. rerun --until HH:MM
    """

    def _run_step(name: str, fn):
        print(f"\n{'=' * 60}", flush=True)
        print(f"[queue] Starting: {name}", flush=True)
        print(f"{'=' * 60}", flush=True)
        t0 = time.monotonic()
        try:
            fn()
            elapsed = time.monotonic() - t0
            print(f"[queue] Finished: {name} in {elapsed:.1f}s", flush=True)
        except Exception as exc:
            elapsed = time.monotonic() - t0
            logger.error("[queue] %s FAILED after %.1fs: %s", name, elapsed, exc)
            print(f"[queue] FAILED: {name} after {elapsed:.1f}s: {exc}", flush=True)

    # Step 1: failure demo
    def _failure_demo():
        from reprobox.harness.failure_demo import run_failure_demo

        run_failure_demo(case_id="dev-001")

    _run_step("failure-demo", _failure_demo)

    # Step 2: containment
    def _containment():
        from reprobox.harness.containment import run_containment_test

        run_containment_test()

    _run_step("containment", _containment)

    # Step 3: interrupt test
    def _interrupt():
        from reprobox.harness.interrupt_test import run_interrupt_test

        ok = run_interrupt_test(case_id="dev-002")
        if not ok:
            raise RuntimeError("Interrupt test returned failure status")

    _run_step("interrupt-test", _interrupt)

    # Step 4: rerun cases until deadline
    def _rerun():
        from reprobox.harness.rerun import run_rerun

        run_rerun(until=until)

    _run_step(f"rerun --until {until}", _rerun)

    print("\n[queue] All steps complete.", flush=True)
