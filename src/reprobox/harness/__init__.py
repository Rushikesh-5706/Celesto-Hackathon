"""Evaluation, validation, demo, and report generation harnesses."""

from reprobox.harness.concurrency import run_concurrency_harness
from reprobox.harness.containment import run_containment_test
from reprobox.harness.evaluation import run_evaluation_batch
from reprobox.harness.failure_demo import run_failure_demo
from reprobox.harness.live_demo import run_live_demo
from reprobox.harness.reports import build_all_reports
from reprobox.harness.stats import compute_median, compute_p90, compute_summary_stats
from reprobox.harness.sweep import run_orphan_sweep
from reprobox.harness.validate_cases import validate_all_cases

__all__ = [
    "run_evaluation_batch",
    "validate_all_cases",
    "run_failure_demo",
    "run_containment_test",
    "run_concurrency_harness",
    "run_orphan_sweep",
    "run_live_demo",
    "build_all_reports",
    "compute_median",
    "compute_p90",
    "compute_summary_stats",
]
